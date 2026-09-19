from collections import defaultdict, deque

from telegram_llm_bot.domain import ChatMessage


class MemoryService:
    def __init__(self, limit: int = 10) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 0 < limit <= 10:
            raise ValueError("memory limit must be an integer between 1 and 10")
        self._messages: dict[int, deque[ChatMessage]] = defaultdict(
            lambda: deque(maxlen=limit)
        )

    def get(self, user_id: int) -> list[ChatMessage]:
        return list(self._messages[user_id])

    def add(self, user_id: int, message: ChatMessage) -> None:
        self._messages[user_id].append(message)
