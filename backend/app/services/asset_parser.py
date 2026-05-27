import csv
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.services.llm_client import llm_client


class ParsedAsset(BaseModel):
    """Normalized business constraints extracted from an uploaded/local asset."""

    structured_data: dict[str, Any] = Field(
        default_factory=dict,
        description="整理后的业务数据",
    )
    hard_constraints: list[str] = Field(
        default_factory=list,
        description="绝对不能违反的硬性条件",
    )
    soft_constraints: list[str] = Field(
        default_factory=list,
        description="建议参考的软性条件",
    )


class AssetParserError(RuntimeError):
    """Raised when a document cannot be read or parsed into ParsedAsset."""


def _read_local_asset(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return path.read_text(encoding="utf-8")

    if suffix == ".csv":
        # Normalize CSV into JSON rows so the LLM receives stable structure.
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        return json.dumps(rows, ensure_ascii=False, indent=2)

    raise AssetParserError(f"Unsupported file type: {suffix}. Only .txt and .csv are supported.")


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """Parse a strict JSON object, tolerating accidental Markdown code fences."""

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        cleaned = cleaned.removesuffix("```").strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AssetParserError("LLM response is not valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise AssetParserError("LLM response must be a JSON object.")

    return parsed


def _build_messages(
    *,
    document_content: str,
    objective: str,
    previous_error: str | None = None,
) -> list[dict[str, str]]:
    schema_hint = ParsedAsset.model_json_schema()
    correction = ""
    if previous_error:
        correction = (
            "\n上一次输出无法通过 JSON/Pydantic 校验，错误如下："
            f"\n{previous_error}\n请修正后只返回合法 JSON。"
        )

    return [
        {
            "role": "system",
            "content": (
                "你是 PAOS 的业务资产解析器。"
                "你的任务是从文档中提取可执行的业务数据和约束条件。"
                "必须只返回 JSON 对象，不要返回 Markdown、解释、注释或多余文本。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"解析目标：{objective}\n\n"
                "请严格返回符合以下 Pydantic Schema 的 JSON：\n"
                f"{json.dumps(schema_hint, ensure_ascii=False, indent=2)}\n\n"
                "字段要求：\n"
                "- structured_data: 整理后的业务数据，必须是 JSON object。\n"
                "- hard_constraints: 绝对不能违反的硬性条件，必须是字符串数组。\n"
                "- soft_constraints: 建议参考的软性条件，必须是字符串数组。\n"
                f"{correction}\n\n"
                "待解析文档内容：\n"
                f"{document_content}"
            ),
        },
    ]


async def parse_document_to_json(file_path: str, objective: str) -> ParsedAsset:
    """Read a txt/csv file and extract business constraints with LLM validation.

    The function makes one initial attempt plus two retries when the LLM returns
    malformed JSON or data that does not match ParsedAsset.
    """

    document_content = _read_local_asset(file_path)
    last_error: str | None = None

    for _attempt in range(3):
        messages = _build_messages(
            document_content=document_content,
            objective=objective,
            previous_error=last_error,
        )
        raw_response = await llm_client.chat(messages)

        try:
            json_payload = _extract_json_object(raw_response)
            return ParsedAsset.model_validate(json_payload)
        except (AssetParserError, ValidationError) as exc:
            last_error = str(exc)

    raise AssetParserError(f"Failed to parse asset after 3 attempts: {last_error}")
