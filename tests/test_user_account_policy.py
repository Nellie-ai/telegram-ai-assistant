import pytest

from telegram_llm_bot.domain import ProfileName
from telegram_llm_bot.user_account.domain import AccountProfile, PolicyAction
from telegram_llm_bot.user_account.policy import UserAccountPolicy


def policy(
    *,
    debt_paid: bool = False,
    paid_profile: ProfileName = ProfileName.DEFAULT,
) -> UserAccountPolicy:
    return UserAccountPolicy(
        owner_user_id=1,
        close_relative_ids={2, 3},
        dinesh_domestic_id=4,
        dinesh_debt_id=5,
        dinesh_debt_paid=debt_paid,
        dinesh_debt_paid_profile=paid_profile,
        blocklist_ids={6, 7},
    )


@pytest.mark.parametrize("sender_id", [2, 3])
def test_close_relative_passes_through_without_llm(sender_id: int) -> None:
    decision = policy().decide(sender_id)

    assert decision.action is PolicyAction.PASS_THROUGH
    assert decision.profile is AccountProfile.CLOSE_RELATIVE


def test_dinesh_domestic_would_reply_with_domestic_profile() -> None:
    decision = policy().decide(4)

    assert decision.action is PolicyAction.WOULD_REPLY
    assert decision.profile is AccountProfile.DINESH_DOMESTIC


def test_unpaid_dinesh_debt_would_block_without_llm() -> None:
    decision = policy(debt_paid=False).decide(5)

    assert decision.action is PolicyAction.WOULD_BLOCK
    assert decision.profile is AccountProfile.DINESH_DEBT


def test_paid_dinesh_debt_uses_configured_fallback() -> None:
    decision = policy(debt_paid=True).decide(5)

    assert decision.action is PolicyAction.WOULD_REPLY
    assert decision.profile is AccountProfile.DEFAULT


def test_paid_dinesh_debt_supports_non_default_fallback() -> None:
    decision = policy(
        debt_paid=True,
        paid_profile=ProfileName.DINESH_DOMESTIC,
    ).decide(5)

    assert decision.action is PolicyAction.WOULD_REPLY
    assert decision.profile is AccountProfile.DINESH_DOMESTIC


def test_explicit_blocklist_would_block() -> None:
    decision = policy().decide(6)

    assert decision.action is PolicyAction.WOULD_BLOCK
    assert decision.profile is AccountProfile.BLOCKLIST


def test_unknown_sender_uses_default() -> None:
    decision = policy().decide(999)

    assert decision.action is PolicyAction.WOULD_REPLY
    assert decision.profile is AccountProfile.DEFAULT


def test_owner_policy_is_pass_through_as_defense_in_depth() -> None:
    decision = policy().decide(1)

    assert decision.action is PolicyAction.PASS_THROUGH
    assert decision.profile is AccountProfile.OWNER


def test_close_relative_precedes_all_other_categories() -> None:
    overlapping = UserAccountPolicy(
        owner_user_id=1,
        close_relative_ids={8, 9},
        dinesh_domestic_id=8,
        dinesh_debt_id=9,
        dinesh_debt_paid=False,
        dinesh_debt_paid_profile=ProfileName.DEFAULT,
        blocklist_ids={8, 9},
    )

    domestic = overlapping.decide(8)
    debt = overlapping.decide(9)

    assert domestic.action is PolicyAction.PASS_THROUGH
    assert domestic.profile is AccountProfile.CLOSE_RELATIVE
    assert debt.action is PolicyAction.PASS_THROUGH
    assert debt.profile is AccountProfile.CLOSE_RELATIVE
