import hashlib
import hmac
import logging
import secrets
from collections.abc import Callable
from typing import Any, Protocol

from telethon import TelegramClient, events

from telegram_llm_bot.user_account.auth import (
    AuthInput,
    ConsoleAuthInput,
    authorize_and_verify_owner,
)
from telegram_llm_bot.user_account.config import UserAccountSettings
from telegram_llm_bot.user_account.domain import PolicyDecision
from telegram_llm_bot.user_account.policy import UserAccountPolicy
from telegram_llm_bot.user_account.safe_logging import configure_safe_telethon_logging

logger = logging.getLogger(__name__)


class UserAccountClient(Protocol):
    def add_event_handler(self, callback: Callable[..., Any], event: Any) -> None: ...

    async def connect(self) -> Any: ...

    async def get_me(self) -> Any: ...

    async def send_code_request(self, phone: str) -> Any: ...

    async def sign_in(self, *args: Any, **kwargs: Any) -> Any: ...

    async def run_until_disconnected(self) -> Any: ...

    async def disconnect(self) -> Any: ...


class UserAccountListener:
    def __init__(
        self,
        settings: UserAccountSettings,
        policy: UserAccountPolicy,
        sender_ref_key: bytes,
    ) -> None:
        self._settings = settings
        self._policy = policy
        self._sender_ref_key = sender_ref_key

    async def handle_event(self, event: Any) -> PolicyDecision | None:
        if not bool(getattr(event, "is_private", False)):
            return None
        if bool(getattr(event, "out", False)):
            return None

        message = getattr(event, "message", None)
        if message is None or getattr(message, "action", None) is not None:
            return None

        sender_id = getattr(event, "sender_id", None)
        if sender_id is None or sender_id == self._settings.owner_user_id:
            return None

        decision = self._policy.decide(sender_id)
        logger.info(
            "User-account dry-run sender_ref=%s profile=%s action=%s",
            _sender_reference(sender_id, self._sender_ref_key),
            decision.profile.value,
            decision.action.value,
        )
        return decision


def _sender_reference(sender_id: int, key: bytes) -> str:
    digest = hmac.new(
        key,
        str(sender_id).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"u:{digest[:10]}"


async def run_user_account_listener(
    settings: UserAccountSettings,
    client_factory: Callable[[str, int, str], UserAccountClient] = TelegramClient,
    auth_input: AuthInput | None = None,
) -> None:
    if settings.dry_run is not True:
        raise ValueError("Stage 2 requires dry-run mode")
    configure_safe_telethon_logging()
    policy = UserAccountPolicy.from_settings(settings)
    listener = UserAccountListener(settings, policy, secrets.token_bytes(32))
    client = client_factory(
        settings.telegram_session_name,
        settings.telegram_api_id,
        settings.telegram_api_hash.get_secret_value(),
    )
    try:
        await authorize_and_verify_owner(
            client,
            settings.owner_user_id,
            auth_input or ConsoleAuthInput(),
        )
        client.add_event_handler(
            listener.handle_event,
            events.NewMessage(incoming=True),
        )
        await client.run_until_disconnected()
    finally:
        await client.disconnect()
