import io
import logging
import struct
from typing import Any

import pytest
from telethon import TelegramClient
from telethon.errors import TypeNotFoundError
from telethon.sessions import MemorySession

from telegram_llm_bot.user_account import __main__ as user_account_main
from telegram_llm_bot.user_account.safe_logging import (
    configure_safe_telethon_logging,
)


@pytest.fixture
def restore_telethon_logger() -> Any:
    logger = logging.getLogger("telethon")
    original = (list(logger.handlers), logger.level, logger.propagate)
    try:
        yield
    finally:
        logger.handlers = original[0]
        logger.setLevel(original[1])
        logger.propagate = original[2]


def test_serialization_error_does_not_log_request_or_arguments(
    restore_telethon_logger: None,
) -> None:
    secret = "SYNTHETIC_SERIALIZATION_SECRET"
    stream = io.StringIO()
    configure_safe_telethon_logging(stream)

    class InvalidRequest:
        def __bytes__(self) -> bytes:
            raise struct.error(secret)

        def __repr__(self) -> str:
            return f"InvalidRequest({secret})"

    client = TelegramClient(MemorySession(), 12345, "SYNTHETIC_API_HASH")
    client._sender._user_connected = True
    try:
        with pytest.raises(struct.error):
            client._sender.send(InvalidRequest())
    finally:
        client._sender._user_connected = False
        client.disconnect()

    rendered = stream.getvalue()
    assert "category=error" in rendered
    assert secret not in rendered
    assert "InvalidRequest" not in rendered


def test_type_not_found_error_does_not_log_raw_payload_or_traceback(
    restore_telethon_logger: None,
) -> None:
    secret = b"SYNTHETIC_PRIVATE_RAW_PAYLOAD"
    stream = io.StringIO()
    configure_safe_telethon_logging(stream)
    logger = logging.getLogger("telethon.client.updates")

    try:
        raise TypeNotFoundError(0, secret)
    except TypeNotFoundError:
        logger.exception("update failure payload=%r", secret)

    rendered = stream.getvalue()
    assert "category=error" in rendered
    assert secret.decode() not in rendered
    assert "Traceback" not in rendered
    assert "TypeNotFoundError" not in rendered


def test_startup_error_reports_only_safe_category(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    restore_telethon_logger: None,
) -> None:
    secret = "SYNTHETIC_PHONE_HASH_SESSION_MESSAGE"

    def fail_settings() -> None:
        raise ValueError(secret)

    monkeypatch.setattr(user_account_main, "get_user_account_settings", fail_settings)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as raised:
            user_account_main.run()

    output = capsys.readouterr()
    rendered = caplog.text + output.out + output.err
    assert raised.value.code == 1
    assert "category=startup_error" in rendered
    assert secret not in rendered
    assert "Traceback" not in rendered
