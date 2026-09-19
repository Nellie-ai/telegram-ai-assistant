from functools import lru_cache
from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from telegram_llm_bot.domain import ProfileName


class UserAccountSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    telegram_api_id: int = Field(gt=0, le=2_147_483_647)
    telegram_api_hash: SecretStr
    telegram_session_name: str = "son-of-anton"

    owner_user_id: int = Field(gt=0)
    close_relative_ids: set[int] = Field(default_factory=set)
    dinesh_domestic_id: int | None = Field(default=None, gt=0)
    dinesh_debt_id: int | None = Field(default=None, gt=0)
    dinesh_debt_paid: bool = False
    dinesh_debt_paid_profile: ProfileName = ProfileName.DEFAULT
    blocklist_ids: set[int] = Field(default_factory=set)

    dry_run: bool = True

    @field_validator("dry_run")
    @classmethod
    def require_dry_run(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Stage 2 requires dry-run mode")
        return value

    @field_validator("telegram_api_hash")
    @classmethod
    def reject_empty_hash(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Telegram API hash must not be empty")
        return value

    @field_validator("telegram_session_name")
    @classmethod
    def reject_empty_session_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Telegram session name must not be empty")
        return cleaned

    @field_validator("close_relative_ids", "blocklist_ids")
    @classmethod
    def reject_invalid_ids(cls, value: set[int]) -> set[int]:
        if any(user_id <= 0 for user_id in value):
            raise ValueError("Telegram user IDs must be positive")
        return value

    @field_validator("dinesh_debt_paid_profile")
    @classmethod
    def validate_paid_profile(cls, value: ProfileName) -> ProfileName:
        allowed = {ProfileName.DEFAULT, ProfileName.DINESH_DOMESTIC}
        if value not in allowed:
            raise ValueError("paid debt profile must be a reply profile")
        return value

    @model_validator(mode="after")
    def reject_special_id_collisions(self) -> Self:
        special_ids = {
            "DINESH_DOMESTIC_ID": self.dinesh_domestic_id,
            "DINESH_DEBT_ID": self.dinesh_debt_id,
        }
        configured = {
            name: user_id for name, user_id in special_ids.items() if user_id is not None
        }
        if len(set(configured.values())) != len(configured):
            raise ValueError("special Telegram user IDs must be distinct")
        if self.owner_user_id in configured.values():
            raise ValueError("special Telegram user IDs must differ from owner")
        return self


@lru_cache
def get_user_account_settings() -> UserAccountSettings:
    return UserAccountSettings()  # type: ignore[call-arg]
