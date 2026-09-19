import asyncio
import logging

from aiogram import Bot, Dispatcher

from telegram_llm_bot.config import Settings
from telegram_llm_bot.handlers import create_router
from telegram_llm_bot.services.bot_service import BotService
from telegram_llm_bot.services.llm import OpenAICompatibleClient
from telegram_llm_bot.services.memory import MemoryService
from telegram_llm_bot.services.profile_router import ProfileRouter

SHUTDOWN_DRAIN_SECONDS = 30.0


async def drain_update_tasks(
    dispatcher: Dispatcher, timeout_seconds: float = SHUTDOWN_DRAIN_SECONDS
) -> None:
    # aiogram registers polling updates here before filters and middlewares run.
    tasks = tuple(dispatcher._handle_update_tasks)
    if not tasks:
        return

    _, pending = await asyncio.wait(tasks, timeout=timeout_seconds)
    if pending:
        logging.getLogger(__name__).warning(
            "Cancelling unfinished Telegram updates count=%s", len(pending)
        )
        for task in pending:
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def run_bot(settings: Settings) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    llm: OpenAICompatibleClient | None = None
    dispatcher: Dispatcher | None = None
    try:
        llm = OpenAICompatibleClient(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
        service = BotService(
            profile_router=ProfileRouter(settings.user_profiles),
            memory=MemoryService(settings.memory_limit),
            llm=llm,
            prompts=settings.prompts,
            ignore_silent=settings.ignore_silent,
            ignore_reply=settings.ignore_reply,
        )
        dispatcher = Dispatcher()
        dispatcher.include_router(create_router(service))
        await dispatcher.start_polling(bot, close_bot_session=False)
    finally:
        try:
            if dispatcher is not None:
                await drain_update_tasks(dispatcher)
        finally:
            try:
                if llm is not None:
                    await llm.close()
            finally:
                await bot.session.close()
