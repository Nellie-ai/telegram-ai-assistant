from dataclasses import dataclass
from enum import StrEnum


class ProfileName(StrEnum):
    OWNER = "OWNER"
    DEFAULT = "DEFAULT"
    IGNORE = "IGNORE"
    DINESH_DEBT = "DINESH_DEBT"
    DINESH_DOMESTIC = "DINESH_DOMESTIC"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class BotReply:
    text: str | None

