import asyncio
import logging
from collections.abc import Awaitable, Callable

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import Message

from telegram_llm_bot.services.bot_service import BotService

TELEGRAM_MESSAGE_LIMIT = 4096
logger = logging.getLogger(__name__)
Sleep = Callable[[float], Awaitable[None]]


def split_telegram_text(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    return [text[index : index + limit] for index in range(0, len(text), limit)]


async def send_telegram_reply(
    message: Message,
    text: str,
    *,
    max_retries: int = 1,
    sleep: Sleep = asyncio.sleep,
) -> bool:
    for chunk in split_telegram_text(text):
        retries = 0
        while True:
            try:
                await message.answer(chunk)
                break
            except TelegramRetryAfter as exc:
                if retries >= max_retries:
                    logger.warning("Telegram send failed category=retry_exhausted")
                    return False
                retries += 1
                logger.warning(
                    "Telegram send retry category=rate_limit attempt=%s", retries
                )
                await sleep(max(0, exc.retry_after))
            except TelegramAPIError as exc:
                logger.warning(
                    "Telegram send failed category=%s", type(exc).__name__
                )
                return False
    return True


def create_router(service: BotService) -> Router:
    router = Router()

    @router.message(F.chat.type == ChatType.PRIVATE)
    async def handle_message(message: Message) -> None:
        if message.from_user is None:
            return

        async def deliver(text: str) -> bool:
            return await send_telegram_reply(message, text)

        await service.handle_text(
            message.from_user.id,
            message.text or "",
            deliver=deliver,
        )

    return router
