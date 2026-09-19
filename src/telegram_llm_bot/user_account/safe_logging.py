import logging
from typing import TextIO


class SafeTelethonLogFilter(logging.Filter):
    """Replace Telethon records before any request or payload is formatted."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = "Telethon internal event category=%s"
        record.args = (record.levelname.lower(),)
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def configure_safe_telethon_logging(stream: TextIO | None = None) -> None:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler.addFilter(SafeTelethonLogFilter())

    telethon_logger = logging.getLogger("telethon")
    for name, child in logging.Logger.manager.loggerDict.items():
        if name.startswith("telethon.") and isinstance(child, logging.Logger):
            child.handlers.clear()
            child.propagate = True
    telethon_logger.handlers.clear()
    telethon_logger.addHandler(handler)
    telethon_logger.propagate = False
    telethon_logger.setLevel(logging.WARNING)
