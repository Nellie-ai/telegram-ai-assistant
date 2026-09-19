import asyncio
import logging
from datetime import datetime, timezone

import pytest
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, User

from telegram_llm_bot.handlers import (
    create_router,
    send_telegram_reply,
    split_telegram_text,
)
from telegram_llm_bot.domain import ProfileName
from telegram_llm_bot.services.bot_service import BotService
from telegram_llm_bot.services.memory import MemoryService
from telegram_llm_bot.services.profile_router import ProfileRouter


class StubService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def handle_text(self, user_id: int, text: str, deliver=None) -> None:
        self.calls.append((user_id, text))


def make_message(chat_type: ChatType, text: str | None = "hello") -> Message:
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=100, type=chat_type),
        from_user=User(id=1, is_bot=False, first_name="Test"),
        text=text,
    )


@pytest.mark.parametrize(
    "chat_type", [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]
)
def test_non_private_message_does_not_reach_business_logic(
    chat_type: ChatType,
) -> None:
    async def scenario() -> tuple[list[tuple[int, str]], bool]:
        service = StubService()
        router = create_router(service)  # type: ignore[arg-type]
        await router.propagate_event("message", make_message(chat_type))
        private_matches, _ = await router.message.handlers[0].check(
            make_message(ChatType.PRIVATE)
        )
        return service.calls, private_matches

    calls, private_matches = asyncio.run(scenario())

    assert calls == []
    assert private_matches is True


@pytest.mark.parametrize(
    ("size", "expected_lengths"),
    [(4096, [4096]), (4097, [4096, 1]), (9000, [4096, 4096, 808])],
)
def test_telegram_reply_boundaries(size: int, expected_lengths: list[int]) -> None:
    text = "😀" * size
    chunks = split_telegram_text(text)

    assert [len(chunk) for chunk in chunks] == expected_lengths
    assert "".join(chunks) == text


def test_retry_after_retries_once() -> None:
    class RetryMessage:
        def __init__(self) -> None:
            self.calls = 0

        async def answer(self, _: str) -> None:
            self.calls += 1
            if self.calls == 1:
                raise TelegramRetryAfter(
                    method=SendMessage(chat_id=1, text="dummy"),
                    message="private provider detail",
                    retry_after=2,
                )

    async def scenario() -> tuple[bool, int, list[float]]:
        message = RetryMessage()
        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        delivered = await send_telegram_reply(
            message, "answer", sleep=fake_sleep  # type: ignore[arg-type]
        )
        return delivered, message.calls, sleeps

    assert asyncio.run(scenario()) == (True, 2, [2])


def test_network_send_failure_is_safe(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_detail = "PRIVATE_TELEGRAM_ERROR"

    class FailingMessage:
        async def answer(self, _: str) -> None:
            raise TelegramNetworkError(
                method=SendMessage(chat_id=1, text="dummy"),
                message=private_detail,
            )

    with caplog.at_level(logging.WARNING):
        delivered = asyncio.run(
            send_telegram_reply(FailingMessage(), "answer")  # type: ignore[arg-type]
        )

    assert delivered is False
    assert "category=TelegramNetworkError" in caplog.text
    assert private_detail not in caplog.text


def test_retry_after_is_limited() -> None:
    class AlwaysLimitedMessage:
        async def answer(self, _: str) -> None:
            raise TelegramRetryAfter(
                method=SendMessage(chat_id=1, text="dummy"),
                message="private detail",
                retry_after=0,
            )

    async def no_sleep(_: float) -> None:
        return None

    delivered = asyncio.run(
        send_telegram_reply(
            AlwaysLimitedMessage(),  # type: ignore[arg-type]
            "answer",
            max_retries=1,
            sleep=no_sleep,
        )
    )

    assert delivered is False


def test_non_text_silent_ignore_through_handler() -> None:
    class NeverLLM:
        calls = 0

        async def complete(self, *_: object) -> str:
            self.calls += 1
            return "unexpected"

    llm = NeverLLM()
    memory = MemoryService()
    service = BotService(
        profile_router=ProfileRouter({1: ProfileName.IGNORE}),
        memory=memory,
        llm=llm,
        prompts={item: "prompt" for item in ProfileName},
        ignore_silent=True,
        ignore_reply="ignored",
    )

    async def scenario() -> None:
        router = create_router(service)
        await router.propagate_event(
            "message", make_message(ChatType.PRIVATE, text=None)
        )

    asyncio.run(scenario())

    assert llm.calls == 0
    assert memory.get(1) == []
