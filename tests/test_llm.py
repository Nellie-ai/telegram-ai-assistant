import asyncio
import logging

import httpx
import pytest

from telegram_llm_bot.domain import ChatMessage
from telegram_llm_bot.services.llm import (
    LLMAPIError,
    LLMTimeoutError,
    OpenAICompatibleClient,
)


def run_client(handler: httpx.MockTransport) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(
        api_key="dummy-secret",
        base_url="https://llm.example/v1",
        model="dummy-model",
        timeout_seconds=1,
        transport=handler,
    )


def test_correct_url_and_payload(caplog: pytest.LogCaptureFixture) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": " answer "}}]},
        )

    async def scenario() -> str:
        client = run_client(httpx.MockTransport(handler))
        try:
            return await client.complete(
                "system prompt", [ChatMessage(role="user", content="hello")]
            )
        finally:
            await client.close()

    with caplog.at_level(logging.INFO, logger="httpx"):
        assert asyncio.run(scenario()) == "answer"
    assert captured == {
        "url": "https://llm.example/v1/chat/completions",
        "authorization": "Bearer dummy-secret",
        "payload": {
            "model": "dummy-model",
            "messages": [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "hello"},
            ],
        },
    }
    assert "dummy-secret" not in caplog.text
    assert "hello" not in caplog.text


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_errors_preserve_only_status(status: int) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "private provider response"})

    async def scenario() -> LLMAPIError:
        client = run_client(httpx.MockTransport(handler))
        try:
            with pytest.raises(LLMAPIError) as raised:
                await client.complete("system", [])
            return raised.value
        finally:
            await client.close()

    error = asyncio.run(scenario())
    assert error.category == "http"
    assert error.status_code == status
    assert "private provider response" not in str(error)


@pytest.mark.parametrize("kind", ["timeout", "network"])
def test_transport_errors(kind: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if kind == "timeout":
            raise httpx.ReadTimeout("private timeout details", request=request)
        raise httpx.ConnectError("private network details", request=request)

    async def scenario() -> Exception:
        client = run_client(httpx.MockTransport(handler))
        try:
            expected = LLMTimeoutError if kind == "timeout" else LLMAPIError
            with pytest.raises(expected) as raised:
                await client.complete("system", [])
            return raised.value
        finally:
            await client.close()

    error = asyncio.run(scenario())
    if kind == "network":
        assert isinstance(error, LLMAPIError)
        assert error.category == "network"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"choices": None}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}),
    ],
)
def test_invalid_responses(response: httpx.Response) -> None:
    async def scenario() -> LLMAPIError:
        client = run_client(httpx.MockTransport(lambda _: response))
        try:
            with pytest.raises(LLMAPIError) as raised:
                await client.complete("system", [])
            return raised.value
        finally:
            await client.close()

    error = asyncio.run(scenario())
    assert error.category == "invalid_response"
    assert error.status_code is None
