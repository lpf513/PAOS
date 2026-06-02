from typing import Dict, List, Optional

from openai import AsyncOpenAI

from app.core.config import settings


class LLMClient:
    """Thin OpenAI-compatible client wrapper for model provider swaps."""

    def __init__(self) -> None:
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        """Create the OpenAI-compatible client only when an LLM call is made."""

        if self._client is not None:
            return self._client

        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. Set it before calling PAOS LLM features."
            )

        self._client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )
        return self._client

    async def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None) -> str:
        client = self._get_client()
        response = await client.chat.completions.create(
            model=model or settings.DEFAULT_LLM_MODEL,
            messages=messages,
        )
        return response.choices[0].message.content or ""

    async def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        client = self._get_client()
        response = await client.embeddings.create(
            model=model or settings.DEFAULT_EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding


llm_client = LLMClient()
