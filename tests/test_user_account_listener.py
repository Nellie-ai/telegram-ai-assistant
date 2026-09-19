import asyncio
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from telethon import events, types

from telegram_llm_bot.services.llm import OpenAICompatibleClient
from telegram_llm_bot.services.memory import MemoryService
from telegram_llm_bot.user_account.config import UserAccountSettings
from telegram_llm_bot.user_account.domain import AccountProfile, PolicyAction
from telegram_llm_bot.user_account.listener import (
    UserAccountListener,
    _sender_reference,
    run_user_account_listener,
)
from telegram_llm_bot.user_account.policy import UserAccountPolicy


def settings(**overrides: Any) -> UserAccountSettings:
    values: dict[str, Any] = {
        "telegram_api_id": 12345,
        "telegram_api_hash": "SYNTHETIC_API_HASH",
        "telegram_session_name": "fake-session",
        "owner_user_id": 1,
        "close_relative_ids": {2},
        "dinesh_domestic_id": 3,
        "dinesh_debt_id": 4,
        "blocklist_ids": {5},
        "dry_run": True,
    }
    values.update(overrides)
    return UserAccountSettings(_env_file=None, **values)


def event(
    *,
    sender_id: int | None = 99,
    private: bool = True,
    outgoing: bool = False,
    service: bool = False,
    text: str = "PRIVATE_MESSAGE_TEXT",
) -> SimpleNamespace:
    return SimpleNamespace(
        sender_id=sender_id,
        is_private=private,
        out=outgoing,
        raw_text=text,
        sender=SimpleNamespace(
            username="PRIVATE_USERNAME",
            phone="15555550101",
            first_name="PRIVATE_DISPLAY_NAME",
        ),
        message=SimpleNamespace(
            action=object() if service else None,
            message=text,
        ),
    )


def listener(config: UserAccountSettings | None = None) -> UserAccountListener:
    actual = config or settings()
    return UserAccountListener(
        actual,
        UserAccountPolicy.from_settings(actual),
        b"synthetic-test-key" * 2,
    )


def telethon_event(
    *,
    peer: Any,
    sender_id: int | None = 99,
    outgoing: bool = False,
    service: bool = False,
    post: bool = False,
) -> events.NewMessage.Event | None:
    common: dict[str, Any] = {
        "id": 10,
        "peer_id": peer,
        "from_id": types.PeerUser(sender_id) if sender_id is not None else None,
        "date": datetime.now(timezone.utc),
        "out": outgoing,
    }
    if service:
        message = types.MessageService(
            **common,
            action=types.MessageActionHistoryClear(),
        )
    else:
        message = types.Message(
            **common,
            message="PRIVATE_MESSAGE_TEXT",
            post=post,
        )
    update_type = (
        types.UpdateNewChannelMessage
        if isinstance(peer, types.PeerChannel)
        else types.UpdateNewMessage
    )
    update = update_type(message, pts=1, pts_count=1)
    return events.NewMessage.build(update, self_id=1)


async def dispatch_real_event(
    target: UserAccountListener,
    incoming: events.NewMessage.Event | None,
) -> object | None:
    if incoming is None:
        return None
    builder = events.NewMessage(incoming=True)
    await builder.resolve(None)
    if not builder.filter(incoming):
        return None
    return await target.handle_event(incoming)


@pytest.mark.parametrize(
    "incoming",
    [
        telethon_event(peer=types.PeerUser(99), outgoing=True),
        telethon_event(peer=types.PeerUser(1), sender_id=1),
        telethon_event(peer=types.PeerChat(10)),
        telethon_event(peer=types.PeerChannel(11)),
        telethon_event(peer=types.PeerChannel(12), post=True),
        telethon_event(peer=types.PeerUser(99), service=True),
    ],
)
def test_real_ignored_events_do_not_call_policy(
    incoming: events.NewMessage.Event | None,
) -> None:
    configured = settings()

    class SpyPolicy:
        calls: list[int] = []

        def decide(self, sender_id: int) -> object:
            self.calls.append(sender_id)
            raise AssertionError("ignored event reached policy")

    policy = SpyPolicy()
    target = UserAccountListener(configured, policy, b"k" * 32)  # type: ignore[arg-type]

    assert asyncio.run(dispatch_real_event(target, incoming)) is None
    assert policy.calls == []


def test_event_without_sender_does_not_call_policy() -> None:
    configured = settings()

    class SpyPolicy:
        calls: list[int] = []

        def decide(self, sender_id: int) -> object:
            self.calls.append(sender_id)
            raise AssertionError("sender-less event reached policy")

    policy = SpyPolicy()
    target = UserAccountListener(configured, policy, b"k" * 32)  # type: ignore[arg-type]

    assert asyncio.run(target.handle_event(event(sender_id=None))) is None
    assert policy.calls == []


def test_private_incoming_message_is_decided() -> None:
    decision = asyncio.run(listener().handle_event(event(sender_id=3)))

    assert decision is not None
    assert decision.action is PolicyAction.WOULD_REPLY
    assert decision.profile is AccountProfile.DINESH_DOMESTIC


def test_real_private_incoming_message_reaches_policy() -> None:
    decision = asyncio.run(
        dispatch_real_event(
            listener(),
            telethon_event(peer=types.PeerUser(3), sender_id=3),
        )
    )

    assert decision is not None
    assert decision.action is PolicyAction.WOULD_REPLY
    assert decision.profile is AccountProfile.DINESH_DOMESTIC


def test_dry_run_never_calls_actions_llm_or_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden_calls: list[str] = []

    async def forbidden_llm(*_: Any, **__: Any) -> str:
        forbidden_calls.append("llm")
        raise AssertionError("LLM must not run in Stage 2")

    def forbidden_memory(*_: Any, **__: Any) -> None:
        forbidden_calls.append("memory")
        raise AssertionError("memory must not change in Stage 2")

    monkeypatch.setattr(OpenAICompatibleClient, "complete", forbidden_llm)
    monkeypatch.setattr(MemoryService, "add", forbidden_memory)

    class FakeClient:
        def __init__(self) -> None:
            self.handler = None
            self.disconnected = False
            self.send_calls = 0
            self.block_calls = 0

        def add_event_handler(self, callback: Any, _: Any) -> None:
            self.handler = callback

        async def connect(self) -> None:
            return None

        async def get_me(self) -> SimpleNamespace:
            return SimpleNamespace(id=1, bot=False)

        async def send_code_request(self, _: str) -> None:
            raise AssertionError("authorized session must not request a code")

        async def sign_in(self, *_: Any, **__: Any) -> None:
            raise AssertionError("authorized session must not sign in")

        async def run_until_disconnected(self) -> None:
            assert self.handler is not None
            for sender_id in (2, 3, 4, 5, 99):
                await self.handler(event(sender_id=sender_id))

        async def disconnect(self) -> None:
            self.disconnected = True

        async def send_message(self, *_: Any, **__: Any) -> None:
            self.send_calls += 1
            raise AssertionError("send_message must not run in dry-run")

        async def block_user(self, *_: Any, **__: Any) -> None:
            self.block_calls += 1
            raise AssertionError("block_user must not run in dry-run")

        async def delete_messages(self, *_: Any, **__: Any) -> None:
            raise AssertionError("delete_messages must not run in dry-run")

        async def edit_message(self, *_: Any, **__: Any) -> None:
            raise AssertionError("edit_message must not run in dry-run")

        async def send_read_acknowledge(self, *_: Any, **__: Any) -> None:
            raise AssertionError("read status must not change in dry-run")

        async def __call__(self, *_: Any, **__: Any) -> None:
            raise AssertionError("Telegram RPC action must not run in dry-run")

    client = FakeClient()

    def factory(_: str, __: int, ___: str) -> FakeClient:
        return client

    asyncio.run(run_user_account_listener(settings(), client_factory=factory))

    assert client.send_calls == 0
    assert client.block_calls == 0
    assert client.disconnected is True
    assert forbidden_calls == []


def test_runtime_guard_rejects_unvalidated_non_dry_run_settings() -> None:
    unsafe = settings().model_copy(update={"dry_run": False})
    factory_called = False

    def factory(_: str, __: int, ___: str) -> object:
        nonlocal factory_called
        factory_called = True
        return object()

    with pytest.raises(ValueError, match="dry-run"):
        asyncio.run(run_user_account_listener(unsafe, client_factory=factory))  # type: ignore[arg-type]

    assert factory_called is False


def test_logs_contain_only_safe_decision_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    api_hash = "SYNTHETIC_API_HASH_MUST_NOT_LEAK"
    private_text = "PRIVATE_MESSAGE_MUST_NOT_LEAK"
    sender_id = 987654321
    configured = settings(telegram_api_hash=api_hash)

    with caplog.at_level(
        logging.INFO, logger="telegram_llm_bot.user_account.listener"
    ):
        decision = asyncio.run(
            listener(configured).handle_event(
                event(sender_id=sender_id, text=private_text)
            )
        )

    assert decision is not None
    assert "profile=DEFAULT" in caplog.text
    assert "action=WOULD_REPLY" in caplog.text
    assert "sender_ref=u:" in caplog.text
    assert str(sender_id) not in caplog.text
    assert private_text not in caplog.text
    assert api_hash not in caplog.text
    assert configured.telegram_session_name not in caplog.text
    assert "PRIVATE_USERNAME" not in caplog.text
    assert "15555550101" not in caplog.text
    assert "PRIVATE_DISPLAY_NAME" not in caplog.text


def test_sender_reference_is_stable_only_for_one_runtime_key() -> None:
    sender_id = 987654321

    first = _sender_reference(sender_id, b"a" * 32)

    assert first == _sender_reference(sender_id, b"a" * 32)
    assert first != _sender_reference(sender_id, b"b" * 32)
    assert str(sender_id) not in first
