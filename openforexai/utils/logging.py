from __future__ import annotations

import logging
import sys
from typing import cast

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure unified logging for app and third-party libraries.

    Both structlog-based app logs and stdlib logs (for example httpx/httpcore)
    are rendered through the same structlog renderer for consistent output.
    """

    level = getattr(logging, log_level.upper(), logging.INFO)

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
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

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
