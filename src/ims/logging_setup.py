"""Structured logging: JSON lines to a rotating file, readable lines to the console."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from types import TracebackType

import structlog

LOG_FILE_NAME = "ims.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5

_SHARED_PROCESSORS: list[structlog.typing.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]


def configure_logging(log_dir: Path, level: str = "INFO") -> Path:
    """Configures stdlib logging and structlog. Returns the log file path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_FILE_NAME

    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=_SHARED_PROCESSORS,
        )
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.dev.ConsoleRenderer(colors=False),
            ],
            foreign_pre_chain=_SHARED_PROCESSORS,
        )
    )

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    root.setLevel(level.upper())

    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    return log_path


def shutdown_logging() -> None:
    """Flushes and closes all handlers (call on exit and in tests)."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()


def log_uncaught_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> None:
    """``sys.excepthook`` replacement: records crashes in the log file."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    structlog.get_logger("ims.crash").critical(
        "uncaught_exception", exc_info=(exc_type, exc_value, exc_tb)
    )
