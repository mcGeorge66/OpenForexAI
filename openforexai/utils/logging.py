from __future__ import annotations

import logging
import sys
import time

import structlog


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog with human-readable console output for development
    and JSON output suitable for log aggregators in production."""

    level = getattr(logging, log_level.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if sys.stderr.isatty() else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging at the same level so third-party libs work.
    # force=True ensures third-party pre-configured handlers don't keep old formatting.
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        stream=sys.stderr,
        level=level,
        format="%(asctime)s.%(msecs)03dZ [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)

