from openai import AsyncOpenAI

from app.core.config import settings


class LLMClient:
    """Thin OpenAI-compatible client wrapper for model provider swaps."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

    async def chat(self, messages: list[dict[str, str]], model: str | None = None) -> str:
        response = await self._client.chat.completions.create(
            model=model or settings.DEFAULT_LLM_MODEL,
            messages=messages,
        )
        return response.choices[0].message.content or ""

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        response = await self._client.embeddings.create(
            model=model or settings.DEFAULT_EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding


llm_client = LLMClient()
