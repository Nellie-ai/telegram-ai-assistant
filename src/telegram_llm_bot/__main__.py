import asyncio

from telegram_llm_bot.app import run_bot
from telegram_llm_bot.config import get_settings


def run() -> None:
    asyncio.run(run_bot(get_settings()))


if __name__ == "__main__":
    run()

