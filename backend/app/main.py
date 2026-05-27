import asyncio
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from sqlalchemy import select

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.sandbox_executor import execute_in_sandbox
from app.db.session import AsyncSessionLocal
from app.models import DAGTaskNode, TaskStatus
from app.services.arbitration_engine import negotiate_for_project
from app.services.llm_gateway import chat_with_memory


_running_projects: set[int] = set()


def _dependencies_completed(node: DAGTaskNode, completed_node_ids: set[int]) -> bool:
    """A node is executable only when every predecessor has completed."""

    dependencies = node.dependencies or []
    return all(dependency_id in completed_node_ids for dependency_id in dependencies)


def _requires_arbitration(agent_role: str | None) -> bool:
    role = (agent_role or "").lower()
    return any(keyword in role for keyword in ("arbitration", "negotiate", "仲裁", "协商", "冲突"))


def _requires_sandbox(agent_role: str | None) -> bool:
    role = (agent_role or "").lower()
    return any(keyword in role for keyword in ("code", "python", "sandbox", "代码", "脚本", "执行"))


def _extract_python_script(llm_output: str) -> str:
    """Extract a Python fenced block when the LLM wraps generated code."""

    marker = "```python"
    if marker not in llm_output:
        return llm_output.strip()

    code_part = llm_output.split(marker, 1)[1]
    return code_part.split("```", 1)[0].strip()


async def _load_project_nodes(project_id: int) -> list[DAGTaskNode]:
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


async def _execute_node(project_id: int, node: DAGTaskNode) -> None:
    await _update_node_status(node.id, TaskStatus.RUNNING)

    try:
        role = node.assigned_agent_role or "通用 PAOS Agent"

        if _requires_arbitration(role):
            # Convention: arbitration roles can be written as "产品策略|研发合规".
            agent_a_role, _, agent_b_role = role.partition("|")
            await negotiate_for_project(
                project_id=project_id,
                task_desc=node.task_name,
                agent_a_role=agent_a_role or "Agent A",
                agent_b_role=agent_b_role or "Agent B",
            )
        elif _requires_sandbox(role):
            script_prompt = (
                "请根据任务生成可直接运行的 Python 3.11 脚本。"
                "只输出代码，不要输出解释。"
            )
            generated_script = await chat_with_memory(project_id, node.task_name, script_prompt)
            sandbox_result = await asyncio.to_thread(
                execute_in_sandbox,
                _extract_python_script(generated_script),
            )
            if sandbox_result["exit_code"] != 0:
                raise RuntimeError(
                    "Sandbox execution failed: "
                    f"{sandbox_result['stderr'] or sandbox_result['stdout']}"
                )
        else:
            context = f"请以 {role} 的身份完成该 DAG 节点任务，并输出可执行结果。"
            await chat_with_memory(project_id, node.task_name, context)

        await _update_node_status(node.id, TaskStatus.COMPLETED)
    except Exception:
        await _update_node_status(node.id, TaskStatus.BLOCKED)
        raise


async def process_dag(project_id: int) -> None:
    """Run all executable DAG nodes for a project until no node can progress."""

    if project_id in _running_projects:
        return

    _running_projects.add(project_id)
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
                return

            for node in runnable_nodes:
                try:
                    await _execute_node(project_id, node)
                except Exception:
                    # Failed nodes become BLOCKED; independent runnable nodes may still continue.
                    continue
    finally:
        _running_projects.discard(project_id)


def _node_to_status_dict(node: DAGTaskNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "task_name": node.task_name,
        "status": node.status.value,
        "dependencies": node.dependencies or [],
        "assigned_agent_role": node.assigned_agent_role,
    }


def _build_status_tree(nodes: list[DAGTaskNode]) -> list[dict[str, Any]]:
    node_map = {node.id: {**_node_to_status_dict(node), "children": []} for node in nodes}
    roots: list[dict[str, Any]] = []

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


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.API_VERSION,
        description="Persistent Agent OS backend service.",
    )
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


app = create_app()


@app.post("/api/projects/{project_id}/start")
async def start_project_dag(project_id: int, background_tasks: BackgroundTasks) -> dict[str, Any]:
    nodes = await _load_project_nodes(project_id)
    if not nodes:
        raise HTTPException(status_code=404, detail="Project DAG has no task nodes.")

    if project_id in _running_projects:
        return {"project_id": project_id, "status": "already_running"}

    background_tasks.add_task(process_dag, project_id)
    return {"project_id": project_id, "status": "started"}


@app.get("/api/projects/{project_id}/status")
async def get_project_dag_status(project_id: int) -> dict[str, Any]:
    nodes = await _load_project_nodes(project_id)
    if not nodes:
        raise HTTPException(status_code=404, detail="Project DAG has no task nodes.")

    return {
        "project_id": project_id,
        "is_running": project_id in _running_projects,
        "tree": _build_status_tree(nodes),
        "nodes": [_node_to_status_dict(node) for node in nodes],
    }
