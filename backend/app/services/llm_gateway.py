import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import ExperienceLedger, IdentityGraph
from app.services.llm_client import llm_client


TOP_K_EXPERIENCES = 3


def _format_hard_constraints(raw_constraints: Optional[Dict[str, Any]]) -> str:
    """Convert stored JSON constraints into prompt-safe readable text."""

    if not raw_constraints:
        return "暂无硬性约束。"
    return json.dumps(raw_constraints, ensure_ascii=False, indent=2)


def _format_reflections(reflections: List[str]) -> str:
    """Merge retrieved experience reflections into a compact prompt section."""

    if not reflections:
        return "暂无可参考历史经验。"

    return "\n".join(f"{index}. {reflection}" for index, reflection in enumerate(reflections, start=1))


async def _load_hard_constraints(project_id: int) -> str:
    stmt = select(IdentityGraph.hard_constraints).where(IdentityGraph.project_id == project_id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)
        hard_constraints = result.scalar_one_or_none()

    return _format_hard_constraints(hard_constraints)


async def _load_relevant_reflections(project_id: int, current_task: str) -> List[str]:
    task_embedding = await llm_client.embed(current_task)
    distance = ExperienceLedger.embedding.cosine_distance(task_embedding)

    stmt = (
        select(ExperienceLedger.reflection_result)
        .where(
            ExperienceLedger.project_id == project_id,
            ExperienceLedger.reflection_result.is_not(None),
        )
        .order_by(distance)
        .limit(TOP_K_EXPERIENCES)
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(stmt)

    return [reflection for reflection in result.scalars().all() if reflection]


async def chat_with_memory(project_id: int, current_task: str, context: str) -> str:
    """Agent LLM gateway with project identity and vector-retrieved memory.

    Flow:
    A. Load hard constraints from IdentityGraph.
    B. Embed current_task and retrieve top-3 similar ExperienceLedger reflections.
    C. Build the system prompt with constraints and prior lessons.
    D. Send the final request through the unified OpenAI-compatible client.
    """

    hard_constraints = await _load_hard_constraints(project_id)
    reflections = await _load_relevant_reflections(project_id, current_task)
    reflection_result = _format_reflections(reflections)

    system_prompt = (
        f"你是 PAOS 代理。你的最高准则是：{hard_constraints}。"
        f"请参考历史经验避免踩坑：{reflection_result}。"
    )
    user_prompt = f"当前任务：{current_task}\n\n上下文：\n{context}"

    return await llm_client.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
