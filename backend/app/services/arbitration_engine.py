import json
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.services.llm_gateway import chat_with_memory


DEFAULT_ARBITRATION_PROJECT_ID = 1


class DeadlockException(RuntimeError):
    """Raised when agents cannot reach agreement within the loop budget."""


class ArbitrationProtocolException(RuntimeError):
    """Raised when an agent violates the arbitration response protocol."""


class ArbitrationReview(BaseModel):
    """Structured review response that Agent B must return as strict JSON."""

    is_approved: bool
    bounding_boxes: List[str] = Field(
        default_factory=list,
        description="If rejected, concrete modification boundaries Agent A must satisfy.",
    )

    @model_validator(mode="after")
    def rejected_review_must_have_boundaries(self) -> "ArbitrationReview":
        if not self.is_approved and not self.bounding_boxes:
            raise ValueError("Rejected review must include at least one bounding box.")
        return self


def _strip_markdown_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json") :].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[len("```") :].strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[: -len("```")].strip()

    return cleaned


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Parse Agent B JSON, tolerating accidental Markdown code fences only."""

    cleaned = _strip_markdown_fence(raw_text)

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ArbitrationProtocolException("Agent B did not return valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ArbitrationProtocolException("Agent B review must be a JSON object.")

    return payload


def _parse_review(raw_text: str) -> ArbitrationReview:
    try:
        return ArbitrationReview.model_validate(_extract_json_object(raw_text))
    except ValidationError as exc:
        raise ArbitrationProtocolException("Agent B JSON does not match ArbitrationReview.") from exc


def _format_bounding_boxes(bounding_boxes: List[str]) -> str:
    if not bounding_boxes:
        return "暂无额外边界约束。"
    return "\n".join(f"{index}. {item}" for index, item in enumerate(bounding_boxes, start=1))


def _build_agent_a_task(
    *,
    task_desc: str,
    agent_a_role: str,
    agent_b_role: str,
    loop_index: int,
    bounding_boxes: List[str],
) -> Tuple[str, str]:
    current_task = f"{agent_a_role}生成第{loop_index}轮冲突解决方案"
    context = (
        f"业务任务：{task_desc}\n"
        f"你的角色：{agent_a_role}\n"
        f"审核方角色：{agent_b_role}\n\n"
        "请给出可执行的最终方案草案，并主动兼顾审核方关注点。\n"
        "本轮必须满足以下修改边界：\n"
        f"{_format_bounding_boxes(bounding_boxes)}"
    )
    return current_task, context


def _build_agent_b_task(
    *,
    task_desc: str,
    proposal: str,
    agent_a_role: str,
    agent_b_role: str,
) -> Tuple[str, str]:
    current_task = f"{agent_b_role}审核{agent_a_role}的冲突解决方案"
    review_schema = ArbitrationReview.model_json_schema()
    context = (
        f"业务任务：{task_desc}\n"
        f"提案方角色：{agent_a_role}\n"
        f"你的审核角色：{agent_b_role}\n\n"
        "请判断该方案是否满足你的目标、风险边界和合规要求。\n"
        "你必须只返回 JSON，不要返回 Markdown、解释或多余文本。\n"
        "JSON 必须符合以下 Pydantic Schema：\n"
        f"{json.dumps(review_schema, ensure_ascii=False, indent=2)}\n\n"
        "如果 is_approved 为 false，bounding_boxes 必须列出下一轮必须满足的具体修改边界，"
        "例如：必须在预算5万内、必须通过安全审计、不得引入高风险第三方依赖。\n\n"
        "待审核方案：\n"
        f"{proposal}"
    )
    return current_task, context


async def negotiate(
    task_desc: str,
    agent_a_role: str,
    agent_b_role: str,
    max_loops: int = 3,
) -> str:
    """Negotiate a proposal between two agent roles until approved or deadlocked."""

    return await negotiate_for_project(
        project_id=DEFAULT_ARBITRATION_PROJECT_ID,
        task_desc=task_desc,
        agent_a_role=agent_a_role,
        agent_b_role=agent_b_role,
        max_loops=max_loops,
    )


async def negotiate_for_project(
    project_id: int,
    task_desc: str,
    agent_a_role: str,
    agent_b_role: str,
    max_loops: int = 3,
) -> str:
    """Negotiate with the memory and constraints of a specific project."""

    if max_loops < 1:
        raise ValueError("max_loops must be greater than or equal to 1.")

    bounding_boxes: List[str] = []
    latest_proposal = ""

    for loop_index in range(1, max_loops + 1):
        agent_a_task, agent_a_context = _build_agent_a_task(
            task_desc=task_desc,
            agent_a_role=agent_a_role,
            agent_b_role=agent_b_role,
            loop_index=loop_index,
            bounding_boxes=bounding_boxes,
        )
        latest_proposal = await chat_with_memory(
            project_id,
            agent_a_task,
            agent_a_context,
        )

        agent_b_task, agent_b_context = _build_agent_b_task(
            task_desc=task_desc,
            proposal=latest_proposal,
            agent_a_role=agent_a_role,
            agent_b_role=agent_b_role,
        )
        raw_review = await chat_with_memory(
            project_id,
            agent_b_task,
            agent_b_context,
        )
        review = _parse_review(raw_review)

        if review.is_approved:
            return latest_proposal

        bounding_boxes.extend(review.bounding_boxes)

    raise DeadlockException(
        "Negotiation deadlocked after "
        f"{max_loops} loops. Last proposal: {latest_proposal}. "
        f"Unresolved boundaries: {_format_bounding_boxes(bounding_boxes)}"
    )
