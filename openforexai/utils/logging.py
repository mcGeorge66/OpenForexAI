from __future__ import annotations

import logging
import logging.handlers
import re
import sys
from pathlib import Path
from typing import cast

import structlog

_LOG_DIR = Path("logs")

# Telegram requires the bot token inside the URL path, and HTTP clients log the
# URL — so a plain "POST https://api.telegram.org/bot<token>/sendMessage" line
# writes the secret to disk. Anyone holding it can send convincing fake alerts
# through the channel the operator trusts. Redacted centrally so it also covers
# any future code path that builds such a URL.
_SECRET_PATTERNS = (
    (re.compile(r"(/bot)\d{6,}:[A-Za-z0-9_-]{30,}"), r"\1<redacted>"),
)


class _RedactSecrets(logging.Filter):
    """Strip credentials from log records before they reach any handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = message
        for pattern, replacement in _SECRET_PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


# Kept long enough that a failure discovered days later is still reconstructable —
# the 2026-09-14 incident (10 rejected orders over three days) went unnoticed
# precisely because nothing but a transient console stream recorded it.
_BACKUP_DAYS = 30


def normalize_log_level(log_level: str | None) -> str:
    level = str(log_level or "INFO").strip().upper()
    return "DEBUG" if level == "DEBUG" else "INFO"


def configure_logging(log_level: str = "INFO") -> None:
    """Configure unified logging for app and third-party libraries.

    Both structlog-based app logs and stdlib logs (for example httpx/httpcore)
    are rendered through the same structlog renderer for consistent output.
    """

    normalized = normalize_log_level(log_level)
    level = getattr(logging, normalized, logging.INFO)

    renderer = (
        structlog.dev.ConsoleRenderer()
        if sys.stderr.isatty()
        else structlog.processors.JSONRenderer()
    )
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        timestamper,
    ]

    # Route stdlib log records through structlog's renderer.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    redactor = _RedactSecrets()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    handler.addFilter(redactor)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Persist to disk as well — stderr alone is lost the moment the console
    # scrolls or closes. Two files: everything at the configured level, plus a
    # warnings/errors-only file so real problems are findable without grepping
    # the full log. JSON in files (machine-readable for later analysis) even
    # when the console renderer is the human-readable one.
    file_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        for filename, file_level in (
            ("openforexai.log", level),
            ("openforexai_errors.log", logging.WARNING),
        ):
            file_handler = logging.handlers.TimedRotatingFileHandler(
                _LOG_DIR / filename,
                when="midnight",
                backupCount=_BACKUP_DAYS,
                encoding="utf-8",
                delay=True,
            )
            file_handler.setLevel(file_level)
            file_handler.setFormatter(file_formatter)
            file_handler.addFilter(redactor)
            root.addHandler(file_handler)
    except OSError as exc:  # never let logging setup take the app down
        logging.getLogger(__name__).warning("File logging unavailable: %s", exc)

    processors: list[structlog.types.Processor] = [
        *shared_processors,
        cast(structlog.types.Processor, structlog.stdlib.ProcessorFormatter.wrap_for_formatter),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
