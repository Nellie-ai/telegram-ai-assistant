from collections.abc import Sequence
from typing import Protocol

import httpx

from telegram_llm_bot.domain import ChatMessage


class LLMTimeoutError(Exception):
    pass


class LLMAPIError(Exception):
    def __init__(self, category: str, status_code: int | None = None) -> None:
        super().__init__(category)
        self.category = category
        self.status_code = status_code


class LLMClient(Protocol):
    async def complete(
        self, system_prompt: str, messages: Sequence[ChatMessage]
    ) -> str: ...


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
        )

    async def complete(
        self, system_prompt: str, messages: Sequence[ChatMessage]
    ) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *[{"role": item.role, "content": item.content} for item in messages],
            ],
        }
        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError from exc
        except httpx.HTTPStatusError as exc:
            raise LLMAPIError("http", exc.response.status_code) from exc
        except httpx.RequestError as exc:
            raise LLMAPIError("network") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMAPIError("invalid_response") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMAPIError("invalid_response")
        return content.strip()

    async def close(self) -> None:
        await self._client.aclose()
