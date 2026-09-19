from functools import lru_cache

from pydantic import AnyHttpUrl, Field, SecretStr, TypeAdapter, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from telegram_llm_bot.domain import ProfileName


DEFAULT_PROMPTS: dict[ProfileName, str] = {
    ProfileName.OWNER: "You are a concise, capable personal assistant for the bot owner.",
    ProfileName.DEFAULT: "You are a helpful and concise Telegram assistant.",
    ProfileName.IGNORE: "",
    ProfileName.DINESH_DEBT: (
        "Respond politely and briefly. Keep the conversation focused on resolving an outstanding debt."
    ),
    ProfileName.DINESH_DOMESTIC: (
        "Respond politely and briefly to domestic or household matters. Avoid discussing debts."
    ),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    telegram_bot_token: SecretStr
    llm_api_key: SecretStr
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = Field(default=20.0, gt=0)
    user_profiles: dict[int, ProfileName] = Field(default_factory=dict)
    profile_prompts: dict[ProfileName, str] = Field(default_factory=dict)
    ignore_silent: bool = False
    ignore_reply: str = "Сообщение принято."
    memory_limit: int = Field(default=10, gt=0, le=10)

    @field_validator("telegram_bot_token", "llm_api_key")
    @classmethod
    def reject_empty_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("secret must not be empty")
        return value

    @field_validator("llm_base_url")
    @classmethod
    def validate_llm_base_url(cls, value: str) -> str:
        TypeAdapter(AnyHttpUrl).validate_python(value)
        return value.rstrip("/")

    @property
    def prompts(self) -> dict[ProfileName, str]:
        return {**DEFAULT_PROMPTS, **self.profile_prompts}


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
