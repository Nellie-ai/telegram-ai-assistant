import getpass
import re
import sys
import warnings
from typing import Any, Protocol

from telethon.errors import SessionPasswordNeededError


class UserAccountStartupError(RuntimeError):
    category = "startup_error"


class InvalidPhoneError(UserAccountStartupError):
    category = "invalid_phone"


class AuthenticationFailedError(UserAccountStartupError):
    category = "authentication_failed"


class BotAccountRejectedError(UserAccountStartupError):
    category = "bot_account_rejected"


class OwnerAccountMismatchError(UserAccountStartupError):
    category = "owner_account_mismatch"


class AuthInput(Protocol):
    def phone(self) -> str: ...

    def code(self) -> str: ...

    def password(self) -> str: ...


class ConsoleAuthInput:
    def phone(self) -> str:
        return self._read_secret("Telegram phone: ")

    def code(self) -> str:
        return self._read_secret("Telegram auth code: ")

    def password(self) -> str:
        return self._read_secret("Telegram 2FA password: ")

    @staticmethod
    def _read_secret(prompt: str) -> str:
        if not sys.stdin.isatty():
            raise AuthenticationFailedError
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                return getpass.getpass(prompt)
        except getpass.GetPassWarning:
            raise AuthenticationFailedError from None


class AuthClient(Protocol):
    async def connect(self) -> Any: ...

    async def get_me(self) -> Any: ...

    async def send_code_request(self, phone: str) -> Any: ...

    async def sign_in(self, *args: Any, **kwargs: Any) -> Any: ...


async def authorize_and_verify_owner(
    client: AuthClient,
    owner_user_id: int,
    auth_input: AuthInput,
) -> None:
    await client.connect()
    me = await client.get_me()
    if me is None:
        phone = _validated_phone(auth_input.phone())
        await client.send_code_request(phone)
        code = _validated_code(auth_input.code())
        try:
            await client.sign_in(phone=phone, code=code)
        except SessionPasswordNeededError:
            password = auth_input.password()
            if not password:
                raise AuthenticationFailedError from None
            await client.sign_in(password=password)
        me = await client.get_me()

    if me is None:
        raise AuthenticationFailedError
    if bool(getattr(me, "bot", False)):
        raise BotAccountRejectedError
    if getattr(me, "id", None) != owner_user_id:
        raise OwnerAccountMismatchError


def _validated_phone(value: str) -> str:
    normalized = re.sub(r"[\s()\-]", "", value.strip())
    if not re.fullmatch(r"\+?[1-9]\d{4,14}", normalized):
        raise InvalidPhoneError
    return normalized


def _validated_code(value: str) -> str:
    code = value.strip()
    if not re.fullmatch(r"\d{3,10}", code):
        raise AuthenticationFailedError
    return code
