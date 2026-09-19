import pytest

from telegram_llm_bot.domain import ChatMessage
from telegram_llm_bot.services.memory import MemoryService


def test_memory_keeps_last_ten_messages_per_user() -> None:
    memory = MemoryService(limit=10)
    for number in range(12):
        memory.add(1, ChatMessage(role="user", content=str(number)))
    memory.add(2, ChatMessage(role="user", content="other"))

    assert [item.content for item in memory.get(1)] == [str(i) for i in range(2, 12)]
    assert [item.content for item in memory.get(2)] == ["other"]


@pytest.mark.parametrize("limit", [0, 11, -1, True])
def test_memory_rejects_invalid_limit(limit: int) -> None:
    with pytest.raises(ValueError):
        MemoryService(limit=limit)


def test_memory_accepts_limit_ten() -> None:
    memory = MemoryService(limit=10)

    assert memory.get(1) == []
