import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from telegram_llm_bot.config import Settings
from telegram_llm_bot.domain import ProfileName


BASE = {"telegram_bot_token": "123:dummy", "llm_api_key": "dummy-key"}


@pytest.mark.parametrize("field", ["telegram_bot_token", "llm_api_key"])
@pytest.mark.parametrize("value", ["", "   "])
def test_secrets_must_not_be_empty(field: str, value: str) -> None:
    values = {**BASE, field: value}

    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "url", ["ftp://example.com/v1", "not-a-url", "example.com/v1"]
)
def test_base_url_must_be_http_or_https(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **BASE, llm_base_url=url)


@pytest.mark.parametrize("limit", [0, 11])
def test_settings_reject_invalid_memory_limit(limit: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **BASE, memory_limit=limit)


def test_settings_accept_memory_limit_ten() -> None:
    assert Settings(_env_file=None, **BASE, memory_limit=10).memory_limit == 10


def test_custom_prompt_is_merged_once() -> None:
    settings = Settings(
        _env_file=None,
        **BASE,
        profile_prompts={ProfileName.OWNER: "custom owner"},
    )

    assert settings.prompts[ProfileName.OWNER] == "custom owner"
    assert settings.prompts[ProfileName.DEFAULT]


def test_validation_error_hides_environment_secrets() -> None:
    secret = "SYNTHETIC_SECRET_MUST_NOT_LEAK"
    with patch.dict(os.environ, {"LLM_API_KEY": secret}, clear=True):
        with pytest.raises(ValidationError) as raised:
            Settings(_env_file=None)

    assert secret not in str(raised.value)


@pytest.mark.parametrize(
    "raw_profiles",
    ['{broken', '{"1":"TYPO"}', '{"not-an-id":"OWNER"}'],
)
def test_invalid_profiles_json_is_rejected_without_input_echo(
    raw_profiles: str,
) -> None:
    with patch.dict(
        os.environ,
        {
            "TELEGRAM_BOT_TOKEN": BASE["telegram_bot_token"],
            "LLM_API_KEY": BASE["llm_api_key"],
            "USER_PROFILES": raw_profiles,
        },
        clear=True,
    ):
        with pytest.raises(Exception) as raised:
            Settings(_env_file=None)

    assert raw_profiles not in str(raised.value)
