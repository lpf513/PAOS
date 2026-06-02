import asyncio
import os
import tempfile
from typing import Any, Dict, List, Optional, Set

from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.v1.router import api_router
from app.api.v1.endpoints.ws import ws_manager
from app.core.config import settings
from app.core.sandbox_executor import execute_in_sandbox
from app.db.session import AsyncSessionLocal
from app.models import DAGTaskNode, ExperienceLedger, IdentityGraph, Project, TaskStatus
from app.services.arbitration_engine import negotiate_for_project
from app.services.asset_parser import AssetParserError, parse_document_to_json
from app.services.llm_client import llm_client
from app.services.llm_gateway import chat_with_memory


_running_projects: Set[int] = set()


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    raw_content: str = Field(..., min_length=1)
    objective: str = "提取该项目的业务硬性约束、软性约束和结构化业务数据。"


def _dependencies_completed(node: DAGTaskNode, completed_node_ids: Set[int]) -> bool:
    """A node is executable only when every predecessor has completed."""

    dependencies = node.dependencies or []
    return all(dependency_id in completed_node_ids for dependency_id in dependencies)


def _requires_arbitration(agent_role: Optional[str]) -> bool:
    role = (agent_role or "").lower()
    return any(keyword in role for keyword in ("arbitration", "negotiate", "仲裁", "协商", "冲突"))


def _requires_sandbox(agent_role: Optional[str]) -> bool:
    role = (agent_role or "").lower()
    return any(keyword in role for keyword in ("code", "python", "sandbox", "代码", "脚本", "执行"))


def _extract_python_script(llm_output: str) -> str:
    """Extract a Python fenced block when the LLM wraps generated code."""

    marker = "```python"
    if marker not in llm_output:
        return llm_output.strip()

    code_part = llm_output.split(marker, 1)[1]
    return code_part.split("```", 1)[0].strip()


async def _load_project_nodes(project_id: int) -> List[DAGTaskNode]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(DAGTaskNode)
            .where(DAGTaskNode.project_id == project_id)
            .order_by(DAGTaskNode.id)
        )
        return list(result.scalars().all())


async def _update_node_status(node_id: int, status: TaskStatus) -> None:
    async with AsyncSessionLocal() as session:
        node = await session.get(DAGTaskNode, node_id)
        if node is None:
            raise RuntimeError(f"DAG task node {node_id} no longer exists.")

        node.status = status
        await session.commit()


async def _complete_node_with_output(node_id: int, output_data: str) -> None:
    async with AsyncSessionLocal() as session:
        node = await session.get(DAGTaskNode, node_id)
        if node is None:
            raise RuntimeError(f"DAG task node {node_id} no longer exists.")

        node.output_data = output_data
        node.status = TaskStatus.COMPLETED
        await session.commit()


async def _record_node_experience(project_id: int, task_name: str, final_result: str) -> None:
    """Summarize successful execution into reusable memory for future agents."""

    reflection_result = await llm_client.chat(
        [
            {
                "role": "system",
                "content": (
                    "你是 PAOS 的经验沉淀器。请把一次 DAG 任务执行结果总结成未来代理可复用的经验。"
                    "重点输出：任务背景、有效做法、风险/坑点、下次执行建议。"
                ),
            },
            {
                "role": "user",
                "content": f"任务名称：{task_name}\n\n本次最终输出：\n{final_result}",
            },
        ]
    )
    embedding = await llm_client.embed(task_name)

    async with AsyncSessionLocal() as session:
        session.add(
            ExperienceLedger(
                project_id=project_id,
                scenario_summary=task_name,
                embedding=embedding,
                reflection_result=reflection_result,
                success_score=1.0,
            )
        )
        await session.commit()


async def _execute_node(project_id: int, node: DAGTaskNode) -> None:
    await _update_node_status(node.id, TaskStatus.RUNNING)
    await ws_manager.broadcast(
        {
            "type": "log",
            "project_id": project_id,
            "node_id": node.id,
            "message": f"开始执行节点 #{node.id}: {node.task_name}",
        }
    )

    try:
        role = node.assigned_agent_role or "通用 PAOS Agent"
        final_result = ""

        if _requires_arbitration(role):
            # Convention: arbitration roles can be written as "产品策略|研发合规".
            agent_a_role, _, agent_b_role = role.partition("|")
            await ws_manager.broadcast(
                {
                    "type": "log",
                    "project_id": project_id,
                    "node_id": node.id,
                    "message": f"检测到冲突仲裁任务，启动 {agent_a_role or 'Agent A'} 与 {agent_b_role or 'Agent B'} 协商。",
                }
            )
            final_result = await negotiate_for_project(
                project_id=project_id,
                task_desc=node.task_name,
                agent_a_role=agent_a_role or "Agent A",
                agent_b_role=agent_b_role or "Agent B",
            )
            await ws_manager.broadcast(
                {
                    "type": "log",
                    "project_id": project_id,
                    "node_id": node.id,
                    "message": f"节点 #{node.id} 仲裁完成。",
                }
            )
        elif _requires_sandbox(role):
            script_prompt = (
                "请根据任务生成可直接运行的 Python 3.11 脚本。"
                "只输出代码，不要输出解释。"
            )
            await ws_manager.broadcast(
                {
                    "type": "log",
                    "project_id": project_id,
                    "node_id": node.id,
                    "message": f"节点 #{node.id} 正在生成沙盒脚本。",
                }
            )
            generated_script = await chat_with_memory(project_id, node.task_name, script_prompt)
            sandbox_result = await asyncio.to_thread(
                execute_in_sandbox,
                _extract_python_script(generated_script),
            )
            if sandbox_result["exit_code"] != 0:
                await ws_manager.broadcast(
                    {
                        "type": "log",
                        "project_id": project_id,
                        "node_id": node.id,
                        "message": f"节点 #{node.id} 沙盒执行失败: {sandbox_result['stderr'] or sandbox_result['stdout']}",
                    }
                )
                raise RuntimeError(
                    "Sandbox execution failed: "
                    f"{sandbox_result['stderr'] or sandbox_result['stdout']}"
                )
            final_result = sandbox_result["stdout"] or "Sandbox execution completed successfully."
            await ws_manager.broadcast(
                {
                    "type": "log",
                    "project_id": project_id,
                    "node_id": node.id,
                    "message": f"节点 #{node.id} 沙盒执行成功。",
                }
            )
        else:
            context = f"请以 {role} 的身份完成该 DAG 节点任务，并输出可执行结果。"
            await ws_manager.broadcast(
                {
                    "type": "log",
                    "project_id": project_id,
                    "node_id": node.id,
                    "message": f"节点 #{node.id} 调用角色 {role} 处理任务。",
                }
            )
            final_result = await chat_with_memory(project_id, node.task_name, context)

        await _complete_node_with_output(node.id, final_result)
        await ws_manager.broadcast(
            {
                "type": "log",
                "project_id": project_id,
                "node_id": node.id,
                "message": f"节点 #{node.id} 已完成，输出结果已保存。",
            }
        )
        await _record_node_experience(project_id, node.task_name, final_result)
        await ws_manager.broadcast(
            {
                "type": "log",
                "project_id": project_id,
                "node_id": node.id,
                "message": f"节点 #{node.id} 经验已写入 ExperienceLedger。",
            }
        )
    except Exception:
        await _update_node_status(node.id, TaskStatus.BLOCKED)
        await ws_manager.broadcast(
            {
                "type": "log",
                "project_id": project_id,
                "node_id": node.id,
                "message": f"节点 #{node.id} 执行失败，状态已置为 BLOCKED。",
            }
        )
        raise


async def process_dag(project_id: int) -> None:
    """Run all executable DAG nodes for a project until no node can progress."""

    if project_id in _running_projects:
        await ws_manager.broadcast(
            {
                "type": "log",
                "project_id": project_id,
                "message": f"项目 #{project_id} 的 DAG 引擎已在运行，忽略重复启动。",
            }
        )
        return

    _running_projects.add(project_id)
    await ws_manager.broadcast(
        {
            "type": "log",
            "project_id": project_id,
            "message": f"项目 #{project_id} DAG 引擎启动。",
        }
    )
    try:
        while True:
            nodes = await _load_project_nodes(project_id)
            completed_node_ids = {
                node.id for node in nodes if node.status == TaskStatus.COMPLETED
            }
            runnable_nodes = [
                node
                for node in nodes
                if node.status == TaskStatus.PENDING
                and _dependencies_completed(node, completed_node_ids)
            ]

            if not runnable_nodes:
                await ws_manager.broadcast(
                    {
                        "type": "log",
                        "project_id": project_id,
                        "message": f"项目 #{project_id} 当前没有可执行 PENDING 节点，DAG 引擎暂停。",
                    }
                )
                return

            await ws_manager.broadcast(
                {
                    "type": "log",
                    "project_id": project_id,
                    "message": f"发现 {len(runnable_nodes)} 个可执行节点。",
                }
            )
            for node in runnable_nodes:
                try:
                    await _execute_node(project_id, node)
                except Exception:
                    # Failed nodes become BLOCKED; independent runnable nodes may still continue.
                    continue
    finally:
        _running_projects.discard(project_id)


def _node_to_status_dict(node: DAGTaskNode) -> Dict[str, Any]:
    return {
        "id": node.id,
        "task_name": node.task_name,
        "status": node.status.value,
        "dependencies": node.dependencies or [],
        "assigned_agent_role": node.assigned_agent_role,
        "output_data": node.output_data,
    }


def _build_status_tree(nodes: List[DAGTaskNode]) -> List[Dict[str, Any]]:
    node_map = {node.id: {**_node_to_status_dict(node), "children": []} for node in nodes}
    roots: List[Dict[str, Any]] = []

    for node in nodes:
        current = node_map[node.id]
        dependencies = node.dependencies or []
        if not dependencies:
            roots.append(current)
            continue

        attached = False
        for dependency_id in dependencies:
            parent = node_map.get(dependency_id)
            if parent is not None:
                parent["children"].append(current)
                attached = True

        if not attached:
            roots.append(current)

    return roots


async def _parse_raw_project_asset(request: ProjectCreateRequest) -> Dict[str, Any]:
    temp_file_path = ""

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            encoding="utf-8",
            delete=False,
        ) as temp_file:
            temp_file.write(request.raw_content)
            temp_file_path = temp_file.name

        parsed_asset = await parse_document_to_json(temp_file_path, request.objective)
        return {
            "structured_data": parsed_asset.structured_data,
            "hard_constraints": parsed_asset.hard_constraints,
            "soft_constraints": parsed_asset.soft_constraints,
        }
    finally:
        if temp_file_path:
            try:
                os.remove(temp_file_path)
            except FileNotFoundError:
                pass


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.API_VERSION,
        description="Persistent Agent OS backend service.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()


@app.websocket("/api/v1/ws/agent-events")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive and accept optional frontend heartbeat packets.
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.post("/api/projects/create")
async def create_project(request: ProjectCreateRequest) -> Dict[str, int]:
    try:
        parsed_payload = await _parse_raw_project_asset(request)
    except AssetParserError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with AsyncSessionLocal() as session:
        project = Project(name=request.name)
        session.add(project)
        await session.flush()

        identity_graph = IdentityGraph(
            project_id=project.id,
            hard_constraints={
                "items": parsed_payload["hard_constraints"],
                "structured_data": parsed_payload["structured_data"],
                "soft_constraints": parsed_payload["soft_constraints"],
            },
        )
        session.add(identity_graph)
        await session.commit()

        return {"project_id": project.id}


@app.post("/api/projects/{project_id}/start")
async def start_project_dag(project_id: int, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    nodes = await _load_project_nodes(project_id)
    if not nodes:
        raise HTTPException(status_code=404, detail="Project DAG has no task nodes.")

    if project_id in _running_projects:
        return {"project_id": project_id, "status": "already_running"}

    background_tasks.add_task(process_dag, project_id)
    return {"project_id": project_id, "status": "started"}


@app.get("/api/projects/{project_id}/status")
async def get_project_dag_status(project_id: int) -> Dict[str, Any]:
    nodes = await _load_project_nodes(project_id)
    if not nodes:
        raise HTTPException(status_code=404, detail="Project DAG has no task nodes.")

    return {
        "project_id": project_id,
        "is_running": project_id in _running_projects,
        "tree": _build_status_tree(nodes),
        "nodes": [_node_to_status_dict(node) for node in nodes],
    }
