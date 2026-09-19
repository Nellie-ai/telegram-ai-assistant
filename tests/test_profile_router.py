from telegram_llm_bot.domain import ProfileName
from telegram_llm_bot.services.profile_router import ProfileRouter


def test_selects_configured_profile() -> None:
    router = ProfileRouter({1: ProfileName.OWNER, 2: ProfileName.DINESH_DEBT})

    assert router.resolve(1) is ProfileName.OWNER
    assert router.resolve(2) is ProfileName.DINESH_DEBT


def test_unknown_user_gets_default_profile() -> None:
    assert ProfileRouter({}).resolve(999) is ProfileName.DEFAULT

