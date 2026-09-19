import asyncio
import logging

from telegram_llm_bot.user_account.auth import UserAccountStartupError
from telegram_llm_bot.user_account.config import get_user_account_settings
from telegram_llm_bot.user_account.listener import run_user_account_listener
from telegram_llm_bot.user_account.safe_logging import configure_safe_telethon_logging

logger = logging.getLogger(__name__)


def run() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("telegram_llm_bot.user_account").setLevel(logging.INFO)
    configure_safe_telethon_logging()
    try:
        settings = get_user_account_settings()
        asyncio.run(run_user_account_listener(settings))
    except KeyboardInterrupt:
        logger.info("User-account listener stopped category=interrupted")
    except Exception as exc:
        category = (
            exc.category
            if isinstance(exc, UserAccountStartupError)
            else "startup_error"
        )
        logger.error("User-account listener stopped category=%s", category)
        raise SystemExit(1) from None


if __name__ == "__main__":
    run()
