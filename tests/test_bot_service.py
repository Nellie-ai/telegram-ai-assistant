import asyncio
import logging
from collections.abc import Sequence

import pytest

from telegram_llm_bot.domain import ChatMessage, ProfileName
from telegram_llm_bot.services.bot_service import BotService
from telegram_llm_bot.services.llm import LLMAPIError, LLMTimeoutError
from telegram_llm_bot.services.memory import MemoryService
from telegram_llm_bot.services.profile_router import ProfileRouter


class FakeLLM:
    def __init__(self, result: str = "answer", error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    async def complete(
        self, system_prompt: str, messages: Sequence[ChatMessage]
    ) -> str:
        self.calls.append((system_prompt, list(messages)))
        if self.error:
            raise self.error
        return self.result


async def deliver_successfully(_: str) -> bool:
    return True


def make_service(
    profile: ProfileName,
    llm: FakeLLM,
    *,
    user_id: int = 1,
    ignore_silent: bool = False,
    memory: MemoryService | None = None,
    profiles: dict[int, ProfileName] | None = None,
    prompts: dict[ProfileName, str] | None = None,
) -> tuple[BotService, MemoryService]:
    actual_memory = memory or MemoryService()
    service = BotService(
        profile_router=ProfileRouter(profiles or {user_id: profile}),
        memory=actual_memory,
        llm=llm,
        prompts=prompts or {item: f"prompt:{item}" for item in ProfileName},
        ignore_silent=ignore_silent,
        ignore_reply="ignored",
    )
    return service, actual_memory


@pytest.mark.parametrize("text", ["hi", "", "   "])
def test_silent_ignore_has_no_side_effects(text: str) -> None:
    llm = FakeLLM()
    service, memory = make_service(ProfileName.IGNORE, llm, ignore_silent=True)
    deliveries: list[str] = []

    async def deliver(reply: str) -> bool:
        deliveries.append(reply)
        return True

    reply = asyncio.run(service.handle_text(1, text, deliver))

    assert reply.text is None
    assert llm.calls == []
    assert deliveries == []
    assert memory.get(1) == []


@pytest.mark.parametrize("text", ["hi", "", "   "])
def test_non_silent_ignore_only_delivers_static_reply(text: str) -> None:
    llm = FakeLLM()
    service, memory = make_service(ProfileName.IGNORE, llm)
    deliveries: list[str] = []

    async def deliver(reply: str) -> bool:
        deliveries.append(reply)
        return True

    reply = asyncio.run(service.handle_text(1, text, deliver))

    assert reply.text == "ignored"
    assert llm.calls == []
    assert deliveries == ["ignored"]
    assert memory.get(1) == []


@pytest.mark.parametrize(
    "profile",
    [
        ProfileName.DEFAULT,
        ProfileName.OWNER,
        ProfileName.DINESH_DEBT,
        ProfileName.DINESH_DOMESTIC,
    ],
)
def test_regular_profiles_call_llm_with_own_prompt(profile: ProfileName) -> None:
    llm = FakeLLM("ok")
    service, _ = make_service(profile, llm)
    reply = asyncio.run(
        service.handle_text(1, "hello", deliver=deliver_successfully)
    )

    assert reply.text == "ok"
    assert llm.calls[0][0] == f"prompt:{profile}"
    assert llm.calls[0][1][-1] == ChatMessage(role="user", content="hello")


def test_unknown_user_uses_default_through_service() -> None:
    llm = FakeLLM("ok")
    service, _ = make_service(
        ProfileName.OWNER,
        llm,
        profiles={1: ProfileName.OWNER},
    )

    asyncio.run(
        service.handle_text(999, "hello", deliver=deliver_successfully)
    )

    assert llm.calls[0][0] == "prompt:DEFAULT"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (LLMTimeoutError(), "Сервис ответа не успел ответить. Попробуйте ещё раз."),
        (
            LLMAPIError("network"),
            "Сервис ответа временно недоступен. Попробуйте позже.",
        ),
    ],
)
def test_llm_errors_are_safe_and_do_not_update_memory(
    error: Exception, expected: str
) -> None:
    service, memory = make_service(ProfileName.DEFAULT, FakeLLM(error=error))

    reply = asyncio.run(service.handle_text(1, "private input"))

    assert reply.text == expected
    assert memory.get(1) == []


def test_logs_do_not_contain_private_text_or_underlying_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_text = "PRIVATE_MESSAGE_SENTINEL"
    private_error = "PRIVATE_ERROR_SENTINEL"
    error = LLMAPIError("network")
    error.__cause__ = RuntimeError(private_error)
    service, _ = make_service(ProfileName.DEFAULT, FakeLLM(error=error))

    with caplog.at_level(logging.INFO):
        asyncio.run(service.handle_text(1, private_text))

    assert private_text not in caplog.text
    assert private_error not in caplog.text
    assert "category=network" in caplog.text


def test_logs_do_not_contain_llm_response(caplog: pytest.LogCaptureFixture) -> None:
    private_response = "PRIVATE_LLM_RESPONSE_SENTINEL"
    service, _ = make_service(ProfileName.DEFAULT, FakeLLM(private_response))

    with caplog.at_level(logging.INFO):
        asyncio.run(service.handle_text(1, "hello"))

    assert private_response not in caplog.text


def test_failed_delivery_does_not_update_memory() -> None:
    service, memory = make_service(ProfileName.DEFAULT, FakeLLM("answer"))

    async def fail_delivery(_: str) -> bool:
        return False

    asyncio.run(service.handle_text(1, "hello", fail_delivery))

    assert memory.get(1) == []


def test_successful_delivery_updates_memory_as_exchange() -> None:
    service, memory = make_service(ProfileName.DEFAULT, FakeLLM("answer"))

    async def deliver(_: str) -> bool:
        return True

    asyncio.run(service.handle_text(1, "hello", deliver))

    assert memory.get(1) == [
        ChatMessage(role="user", content="hello"),
        ChatMessage(role="assistant", content="answer"),
    ]


def test_missing_delivery_callback_returns_answer_without_memory_update() -> None:
    service, memory = make_service(ProfileName.DEFAULT, FakeLLM("answer"))

    reply = asyncio.run(service.handle_text(1, "hello"))

    assert reply.text == "answer"
    assert memory.get(1) == []


def test_same_user_messages_remain_ordered() -> None:
    async def scenario() -> tuple[list[list[str]], list[str]]:
        first_entered = asyncio.Event()
        release_first = asyncio.Event()

        class ControlledLLM(FakeLLM):
            async def complete(
                self, system_prompt: str, messages: Sequence[ChatMessage]
            ) -> str:
                self.calls.append((system_prompt, list(messages)))
                if messages[-1].content == "first":
                    first_entered.set()
                    await release_first.wait()
                return f"answer:{messages[-1].content}"

        llm = ControlledLLM()
        service, memory = make_service(ProfileName.DEFAULT, llm)
        first = asyncio.create_task(
            service.handle_text(1, "first", deliver=deliver_successfully)
        )
        await first_entered.wait()
        second = asyncio.create_task(
            service.handle_text(1, "second", deliver=deliver_successfully)
        )
        await asyncio.sleep(0)
        assert len(llm.calls) == 1
        release_first.set()
        await asyncio.gather(first, second)
        return (
            [[item.content for item in call[1]] for call in llm.calls],
            [item.content for item in memory.get(1)],
        )

    calls, memory = asyncio.run(scenario())

    assert calls == [
        ["first"],
        ["first", "answer:first", "second"],
    ]
    assert memory == ["first", "answer:first", "second", "answer:second"]


def test_different_users_run_in_parallel() -> None:
    async def scenario() -> None:
        both_entered = asyncio.Event()
        release = asyncio.Event()
        active_users: set[str] = set()

        class ConcurrentLLM(FakeLLM):
            async def complete(
                self, system_prompt: str, messages: Sequence[ChatMessage]
            ) -> str:
                active_users.add(messages[-1].content)
                if len(active_users) == 2:
                    both_entered.set()
                await release.wait()
                return "answer"

        service, _ = make_service(
            ProfileName.DEFAULT,
            ConcurrentLLM(),
            profiles={1: ProfileName.DEFAULT, 2: ProfileName.DEFAULT},
        )
        tasks = [
            asyncio.create_task(
                service.handle_text(1, "user-one", deliver=deliver_successfully)
            ),
            asyncio.create_task(
                service.handle_text(2, "user-two", deliver=deliver_successfully)
            ),
        ]
        await asyncio.wait_for(both_entered.wait(), timeout=1)
        assert active_users == {"user-one", "user-two"}
        release.set()
        await asyncio.gather(*tasks)

    asyncio.run(scenario())
