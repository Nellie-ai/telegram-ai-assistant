import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from telegram_llm_bot.domain import ProfileName
from telegram_llm_bot.user_account.config import UserAccountSettings


BASE = {
    "telegram_api_id": 12345,
    "telegram_api_hash": "fake-api-hash",
    "owner_user_id": 1001,
}


def test_user_account_settings_parse_policy_configuration() -> None:
    settings = UserAccountSettings(
        _env_file=None,
        **BASE,
        close_relative_ids={1002, 1003},
        dinesh_domestic_id=1004,
        dinesh_debt_id=1005,
        dinesh_debt_paid=True,
        dinesh_debt_paid_profile=ProfileName.DINESH_DOMESTIC,
        blocklist_ids={1006},
    )

    assert settings.close_relative_ids == {1002, 1003}
    assert settings.dinesh_debt_paid is True
    assert settings.dinesh_debt_paid_profile is ProfileName.DINESH_DOMESTIC
    assert settings.dry_run is True


def test_dry_run_cannot_be_disabled() -> None:
    with pytest.raises(ValidationError):
        UserAccountSettings(_env_file=None, **BASE, dry_run=False)


@pytest.mark.parametrize("api_id", [0, -1, 2_147_483_648])
def test_api_id_must_fit_positive_telegram_int(api_id: int) -> None:
    with pytest.raises(ValidationError) as raised:
        UserAccountSettings(_env_file=None, **{**BASE, "telegram_api_id": api_id})

    rendered = str(raised.value)
    assert "input_value" not in rendered
    if api_id == 2_147_483_648:
        assert str(api_id) not in rendered


@pytest.mark.parametrize("field", ["telegram_api_hash", "telegram_session_name"])
@pytest.mark.parametrize("value", ["", "   "])
def test_credentials_and_session_name_must_not_be_empty(
    field: str, value: str
) -> None:
    values = {**BASE, field: value}

    with pytest.raises(ValidationError):
        UserAccountSettings(_env_file=None, **values)


def test_environment_json_ids_are_parsed() -> None:
    environment = {
        "TELEGRAM_API_ID": "12345",
        "TELEGRAM_API_HASH": "fake-api-hash",
        "OWNER_USER_ID": "1001",
        "CLOSE_RELATIVE_IDS": "[1002,1003]",
        "BLOCKLIST_IDS": "[1006]",
        "DRY_RUN": "true",
    }
    with patch.dict(os.environ, environment, clear=True):
        settings = UserAccountSettings(_env_file=None)

    assert settings.close_relative_ids == {1002, 1003}
    assert settings.blocklist_ids == {1006}


def test_validation_error_does_not_expose_api_hash() -> None:
    secret = "SYNTHETIC_API_HASH_MUST_NOT_LEAK"
    with patch.dict(os.environ, {"TELEGRAM_API_HASH": secret}, clear=True):
        with pytest.raises(ValidationError) as raised:
            UserAccountSettings(_env_file=None)

    assert secret not in str(raised.value)


@pytest.mark.parametrize(
    "overrides",
    [
        {"dinesh_domestic_id": 2001, "dinesh_debt_id": 2001},
        {"dinesh_domestic_id": BASE["owner_user_id"]},
        {"dinesh_debt_id": BASE["owner_user_id"]},
    ],
)
def test_special_ids_cannot_collide(overrides: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        UserAccountSettings(_env_file=None, **{**BASE, **overrides})
