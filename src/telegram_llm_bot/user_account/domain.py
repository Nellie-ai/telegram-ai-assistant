from dataclasses import dataclass
from enum import StrEnum


class PolicyAction(StrEnum):
    PASS_THROUGH = "PASS_THROUGH"
    WOULD_REPLY = "WOULD_REPLY"
    WOULD_BLOCK = "WOULD_BLOCK"


class AccountProfile(StrEnum):
    OWNER = "OWNER"
    CLOSE_RELATIVE = "CLOSE_RELATIVE"
    DINESH_DOMESTIC = "DINESH_DOMESTIC"
    DINESH_DEBT = "DINESH_DEBT"
    BLOCKLIST = "BLOCKLIST"
    DEFAULT = "DEFAULT"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: PolicyAction
    profile: AccountProfile