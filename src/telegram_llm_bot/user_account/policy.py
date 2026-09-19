from collections.abc import Collection

from telegram_llm_bot.domain import ProfileName
from telegram_llm_bot.user_account.config import UserAccountSettings
from telegram_llm_bot.user_account.domain import (
    AccountProfile,
    PolicyAction,
    PolicyDecision,
)


class UserAccountPolicy:
    def __init__(
        self,
        *,
        owner_user_id: int,
        close_relative_ids: Collection[int],
        dinesh_domestic_id: int | None,
        dinesh_debt_id: int | None,
        dinesh_debt_paid: bool,
        dinesh_debt_paid_profile: ProfileName,
        blocklist_ids: Collection[int],
    ) -> None:
        self._owner_user_id = owner_user_id
        self._close_relative_ids = frozenset(close_relative_ids)
        self._dinesh_domestic_id = dinesh_domestic_id
        self._dinesh_debt_id = dinesh_debt_id
        self._dinesh_debt_paid = dinesh_debt_paid
        self._dinesh_debt_paid_profile = dinesh_debt_paid_profile
        self._blocklist_ids = frozenset(blocklist_ids)

    @classmethod
    def from_settings(cls, settings: UserAccountSettings) -> "UserAccountPolicy":
        return cls(
            owner_user_id=settings.owner_user_id,
            close_relative_ids=settings.close_relative_ids,
            dinesh_domestic_id=settings.dinesh_domestic_id,
            dinesh_debt_id=settings.dinesh_debt_id,
            dinesh_debt_paid=settings.dinesh_debt_paid,
            dinesh_debt_paid_profile=settings.dinesh_debt_paid_profile,
            blocklist_ids=settings.blocklist_ids,
        )

    def decide(self, sender_id: int) -> PolicyDecision:
        if sender_id == self._owner_user_id:
            return PolicyDecision(PolicyAction.PASS_THROUGH, AccountProfile.OWNER)
        if sender_id in self._close_relative_ids:
            return PolicyDecision(
                PolicyAction.PASS_THROUGH, AccountProfile.CLOSE_RELATIVE
            )
        if sender_id == self._dinesh_debt_id:
            if self._dinesh_debt_paid:
                return PolicyDecision(
                    PolicyAction.WOULD_REPLY,
                    AccountProfile(self._dinesh_debt_paid_profile.value),
                )
            return PolicyDecision(
                PolicyAction.WOULD_BLOCK, AccountProfile.DINESH_DEBT
            )
        if sender_id == self._dinesh_domestic_id:
            return PolicyDecision(
                PolicyAction.WOULD_REPLY, AccountProfile.DINESH_DOMESTIC
            )
        if sender_id in self._blocklist_ids:
            return PolicyDecision(
                PolicyAction.WOULD_BLOCK, AccountProfile.BLOCKLIST
            )
        return PolicyDecision(PolicyAction.WOULD_REPLY, AccountProfile.DEFAULT)