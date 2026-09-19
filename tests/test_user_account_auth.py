import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from telethon.errors import SessionPasswordNeededError

from telegram_llm_bot.user_account import auth
from telegram_llm_bot.user_account.auth import (
    BotAccountRejectedError,
    ConsoleAuthInput,
    InvalidPhoneError,
    OwnerAccountMismatchError,
    authorize_and_verify_owner,
)
from telegram_llm_bot.user_account.config import UserAccountSettings
from telegram_llm_bot.user_account.listener import run_user_account_listener


def settings() -> UserAccountSettings:
    return UserAccountSettings(
        _env_file=None,
        telegram_api_id=12345,
        telegram_api_hash="SYNTHETIC_API_HASH",
        telegram_session_name="fake-session",
        owner_user_id=1001,
    )


def test_first_login_uses_hidden_inputs_without_printing_identity(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    phone = "+15555550101"
    code = "12345"
    password = "SYNTHETIC_2FA_PASSWORD"
    display_name = "SYNTHETIC_PRIVATE_DISPLAY_NAME"
    answers = iter([phone, code, password])
    prompts: list[str] = []

    monkeypatch.setattr(
        auth.sys,
        "stdin",
        SimpleNamespace(isatty=lambda: True),
    )

    def hidden_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(auth.getpass, "getpass", hidden_input)

    class FirstLoginClient:
        authorized = False

        async def connect(self) -> None:
            return None

        async def get_me(self) -> SimpleNamespace | None:
            if not self.authorized:
                return None
            return SimpleNamespace(
                id=1001,
                bot=False,
                first_name=display_name,
            )

        async def send_code_request(self, supplied_phone: str) -> None:
            assert supplied_phone == phone

        async def sign_in(self, *_: Any, **kwargs: Any) -> None:
            if "code" in kwargs:
                assert kwargs == {"phone": phone, "code": code}
                raise SessionPasswordNeededError(request=None)
            assert kwargs == {"password": password}
            self.authorized = True

    asyncio.run(
        authorize_and_verify_owner(
            FirstLoginClient(),
            owner_user_id=1001,
            auth_input=ConsoleAuthInput(),
        )
    )

    output = capsys.readouterr()
    rendered = output.out + output.err
    assert phone not in rendered
    assert code not in rendered
    assert password not in rendered
    assert display_name not in rendered
    assert prompts == [
        "Telegram phone: ",
        "Telegram auth code: ",
        "Telegram 2FA password: ",
    ]


def test_getpass_fallback_fails_before_reading_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class UnsafeFallbackInput:
        read_called = False

        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            self.read_called = True
            return "SYNTHETIC_SECRET_MUST_NOT_BE_READ\n"

    unsafe_input = UnsafeFallbackInput()
    monkeypatch.setattr(auth.sys, "stdin", unsafe_input)
    monkeypatch.setattr(
        auth.getpass,
        "getpass",
        auth.getpass.fallback_getpass,
    )

    with pytest.raises(auth.AuthenticationFailedError):
        ConsoleAuthInput().code()

    output = capsys.readouterr()
    assert unsafe_input.read_called is False
    assert "SYNTHETIC_SECRET_MUST_NOT_BE_READ" not in output.out + output.err


def test_bot_token_cannot_be_used_as_phone() -> None:
    class BotTokenInput:
        def phone(self) -> str:
            return "12345:SYNTHETIC_BOT_TOKEN"

        def code(self) -> str:
            raise AssertionError

        def password(self) -> str:
            raise AssertionError

    class UnauthorizedClient:
        code_requests = 0

        async def connect(self) -> None:
            return None

        async def get_me(self) -> None:
            return None

        async def send_code_request(self, _: str) -> None:
            self.code_requests += 1

        async def sign_in(self, *_: Any, **__: Any) -> None:
            raise AssertionError

    client = UnauthorizedClient()

    with pytest.raises(InvalidPhoneError):
        asyncio.run(authorize_and_verify_owner(client, 1001, BotTokenInput()))

    assert client.code_requests == 0


@pytest.mark.parametrize(
    ("identity", "error_type"),
    [
        (SimpleNamespace(id=9999, bot=False), OwnerAccountMismatchError),
        (SimpleNamespace(id=1001, bot=True), BotAccountRejectedError),
    ],
)
def test_unverified_account_never_registers_handler_and_disconnects(
    identity: SimpleNamespace,
    error_type: type[Exception],
) -> None:
    class FakeClient:
        handler_registered = False
        run_called = False
        disconnect_calls = 0

        async def connect(self) -> None:
            return None

        async def get_me(self) -> SimpleNamespace:
            return identity

        async def send_code_request(self, _: str) -> None:
            raise AssertionError

        async def sign_in(self, *_: Any, **__: Any) -> None:
            raise AssertionError

        def add_event_handler(self, *_: Any) -> None:
            self.handler_registered = True

        async def run_until_disconnected(self) -> None:
            self.run_called = True

        async def disconnect(self) -> None:
            self.disconnect_calls += 1

    client = FakeClient()

    with pytest.raises(error_type):
        asyncio.run(
            run_user_account_listener(settings(), client_factory=lambda *_: client)
        )

    assert client.handler_registered is False
    assert client.run_called is False
    assert client.disconnect_calls == 1


def test_handler_is_registered_only_after_owner_verification() -> None:
    calls: list[str] = []

    class FakeClient:
        async def connect(self) -> None:
            calls.append("connect")

        async def get_me(self) -> SimpleNamespace:
            calls.append("get_me")
            return SimpleNamespace(id=1001, bot=False)

        async def send_code_request(self, _: str) -> None:
            raise AssertionError

        async def sign_in(self, *_: Any, **__: Any) -> None:
            raise AssertionError

        def add_event_handler(self, *_: Any) -> None:
            calls.append("add_handler")

        async def run_until_disconnected(self) -> None:
            calls.append("run")

        async def disconnect(self) -> None:
            calls.append("disconnect")

    client = FakeClient()

    asyncio.run(run_user_account_listener(settings(), client_factory=lambda *_: client))

    assert calls == ["connect", "get_me", "add_handler", "run", "disconnect"]
