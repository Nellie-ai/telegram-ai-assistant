import asyncio
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable

from telegram_llm_bot.domain import BotReply, ChatMessage, ProfileName
from telegram_llm_bot.services.llm import LLMAPIError, LLMClient, LLMTimeoutError
from telegram_llm_bot.services.memory import MemoryService
from telegram_llm_bot.services.profile_router import ProfileRouter

logger = logging.getLogger(__name__)
DeliveryCallback = Callable[[str], Awaitable[bool]]


class BotService:
    def __init__(
        self,
        *,
        profile_router: ProfileRouter,
        memory: MemoryService,
        llm: LLMClient,
        prompts: dict[ProfileName, str],
        ignore_silent: bool,
        ignore_reply: str,
    ) -> None:
        self._profile_router = profile_router
        self._memory = memory
        self._llm = llm
        self._prompts = prompts
        self._ignore_silent = ignore_silent
        self._ignore_reply = ignore_reply
        self._user_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def handle_text(
        self,
        user_id: int,
        text: str,
        deliver: DeliveryCallback | None = None,
    ) -> BotReply:
        async with self._user_locks[user_id]:
            profile = self._profile_router.resolve(user_id)
            logger.info("Handling message profile=%s", profile.value)
            if profile is ProfileName.IGNORE:
                reply = None if self._ignore_silent else self._ignore_reply
                if reply is not None:
                    await self._deliver(reply, deliver)
                return BotReply(reply)

            cleaned = text.strip()
            if not cleaned:
                reply = "Отправьте непустое текстовое сообщение."
                await self._deliver(reply, deliver)
                return BotReply(reply)

            user_message = ChatMessage(role="user", content=cleaned)
            history = [*self._memory.get(user_id), user_message]
            try:
                answer = await self._llm.complete(self._prompts[profile], history)
            except LLMTimeoutError:
                logger.warning("LLM request failed category=timeout")
                reply = "Сервис ответа не успел ответить. Попробуйте ещё раз."
                await self._deliver(reply, deliver)
                return BotReply(reply)
            except LLMAPIError as exc:
                logger.warning(
                    "LLM request failed category=%s status=%s",
                    exc.category,
                    exc.status_code,
                )
                reply = "Сервис ответа временно недоступен. Попробуйте позже."
                await self._deliver(reply, deliver)
                return BotReply(reply)

            delivered = await self._deliver(answer, deliver)
            if delivered:
                self._memory.add(user_id, user_message)
                self._memory.add(
                    user_id, ChatMessage(role="assistant", content=answer)
                )
            return BotReply(answer)

    @staticmethod
    async def _deliver(text: str, deliver: DeliveryCallback | None) -> bool:
        if deliver is None:
            return False
        return await deliver(text)
