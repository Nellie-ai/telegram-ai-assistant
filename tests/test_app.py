import asyncio
from datetime import datetime, timezone

import pytest
from aiogram import Dispatcher
from aiogram.dispatcher.event.handler import FilterObject
from aiogram.methods import GetUpdates
from aiogram.types import Chat, Message, Update, User
from aiogram.utils.token import TokenValidationError

from telegram_llm_bot.app import drain_update_tasks, run_bot
from telegram_llm_bot.config import Settings
from telegram_llm_bot.handlers import create_router as real_create_router


def settings(token: str = "123:dummy") -> Settings:
    return Settings(
        _env_file=None,
        telegram_bot_token=token,
        llm_api_key="dummy-key",
    )


@pytest.mark.parametrize("polling_failure", [False, True])
def test_resources_close_once_on_shutdown_or_polling_failure(
    monkeypatch: pytest.MonkeyPatch,
    polling_failure: bool,
) -> None:
    events: list[str] = []

    class FakeSession:
        async def close(self) -> None:
            events.append("telegram-close")

    class FakeBot:
        def __init__(self, _: str) -> None:
            self.session = FakeSession()

    class FakeLLM:
        def __init__(self, **_: object) -> None:
            events.append("llm-created")

        async def close(self) -> None:
            events.append("llm-close")

    class FakeDispatcher:
        def __init__(self) -> None:
            self._handle_update_tasks: set[asyncio.Task[object]] = set()

        def include_router(self, _: object) -> None:
            events.append("router-included")

        async def start_polling(self, _: object, **kwargs: object) -> None:
            assert kwargs == {"close_bot_session": False}
            events.append("polling")
            if polling_failure:
                raise RuntimeError("synthetic polling failure")

    monkeypatch.setattr("telegram_llm_bot.app.Bot", FakeBot)
    monkeypatch.setattr("telegram_llm_bot.app.OpenAICompatibleClient", FakeLLM)
    monkeypatch.setattr("telegram_llm_bot.app.Dispatcher", FakeDispatcher)

    if polling_failure:
        with pytest.raises(RuntimeError, match="synthetic polling failure"):
            asyncio.run(run_bot(settings()))
    else:
        asyncio.run(run_bot(settings()))

    assert events.count("llm-close") == 1
    assert events.count("telegram-close") == 1
    assert events[-2:] == ["llm-close", "telegram-close"]


def test_invalid_telegram_token_does_not_create_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = False

    class FakeLLM:
        def __init__(self, **_: object) -> None:
            nonlocal created
            created = True

    monkeypatch.setattr("telegram_llm_bot.app.OpenAICompatibleClient", FakeLLM)

    secret_token = "SYNTHETIC_TOKEN_MUST_NOT_LEAK"
    with pytest.raises(TokenValidationError) as raised:
        asyncio.run(run_bot(settings(secret_token)))

    assert created is False
    assert secret_token not in str(raised.value)


def test_telegram_session_closes_if_llm_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    telegram_closed = False

    class FakeSession:
        async def close(self) -> None:
            nonlocal telegram_closed
            telegram_closed = True

    class FakeBot:
        def __init__(self, _: str) -> None:
            self.session = FakeSession()

    class FailingLLM:
        def __init__(self, **_: object) -> None:
            pass

        async def close(self) -> None:
            raise RuntimeError("synthetic close failure")

    class FakeDispatcher:
        def __init__(self) -> None:
            self._handle_update_tasks: set[asyncio.Task[object]] = set()

        def include_router(self, _: object) -> None:
            pass

        async def start_polling(self, _: object, **__: object) -> None:
            pass

    monkeypatch.setattr("telegram_llm_bot.app.Bot", FakeBot)
    monkeypatch.setattr("telegram_llm_bot.app.OpenAICompatibleClient", FailingLLM)
    monkeypatch.setattr("telegram_llm_bot.app.Dispatcher", FakeDispatcher)

    with pytest.raises(RuntimeError, match="synthetic close failure"):
        asyncio.run(run_bot(settings()))

    assert telegram_closed is True


def test_shutdown_drains_update_blocked_in_filter_before_closing_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> list[str]:
        events: list[str] = []
        filter_entered = asyncio.Event()
        release_filter = asyncio.Event()
        dispatcher = Dispatcher()

        class FakeSession:
            timeout = None

            async def close(self) -> None:
                events.append("telegram-close")

        class FakeBot:
            id = 123

            def __init__(self, _: str) -> None:
                self.session = FakeSession()
                self.update_sent = False

            async def me(self) -> User:
                return User(
                    id=self.id,
                    is_bot=True,
                    first_name="Dummy",
                    username="dummy_bot",
                )

            async def __call__(self, method: object, **_: object) -> object:
                if isinstance(method, GetUpdates):
                    if not self.update_sent:
                        self.update_sent = True
                        return [
                            Update(
                                update_id=1,
                                message=Message(
                                    message_id=1,
                                    date=datetime.now(timezone.utc),
                                    chat=Chat(id=1, type="private"),
                                    from_user=User(
                                        id=1,
                                        is_bot=False,
                                        first_name="User",
                                    ),
                                    text="hello",
                                ),
                            )
                        ]
                    await asyncio.Event().wait()
                events.append("telegram-send")
                return None

        class FakeLLM:
            def __init__(self, **_: object) -> None:
                pass

            async def complete(self, *_: object) -> str:
                events.append("llm-call")
                return "answer"

            async def close(self) -> None:
                events.append("llm-close")

        async def blocking_filter(_: Message) -> bool:
            events.append("filter-entered")
            filter_entered.set()
            await release_filter.wait()
            events.append("filter-released")
            return True

        def create_router_with_blocking_filter(service: object) -> object:
            router = real_create_router(service)  # type: ignore[arg-type]
            router.message.handlers[0].filters.insert(
                0, FilterObject(callback=blocking_filter)
            )
            return router

        monkeypatch.setattr("telegram_llm_bot.app.Bot", FakeBot)
        monkeypatch.setattr(
            "telegram_llm_bot.app.OpenAICompatibleClient", FakeLLM
        )
        monkeypatch.setattr(
            "telegram_llm_bot.app.Dispatcher", lambda: dispatcher
        )
        monkeypatch.setattr(
            "telegram_llm_bot.app.create_router", create_router_with_blocking_filter
        )

        application = asyncio.create_task(run_bot(settings()))
        await asyncio.wait_for(filter_entered.wait(), timeout=2)
        await dispatcher.stop_polling()
        await asyncio.sleep(0)

        assert not application.done()
        assert "llm-close" not in events
        assert "telegram-close" not in events

        release_filter.set()
        await asyncio.wait_for(application, timeout=2)
        return events

    events = asyncio.run(scenario())

    assert events.index("filter-released") < events.index("llm-call")
    assert events.index("telegram-send") < events.index("llm-close")
    assert events[-2:] == ["llm-close", "telegram-close"]


def test_update_drain_cancels_tasks_after_timeout() -> None:
    async def scenario() -> bool:
        dispatcher = Dispatcher()
        started = asyncio.Event()

        async def stuck_update() -> None:
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(stuck_update())
        dispatcher._handle_update_tasks.add(task)
        await started.wait()
        await drain_update_tasks(dispatcher, timeout_seconds=0)
        return task.cancelled()

    assert asyncio.run(scenario()) is True
