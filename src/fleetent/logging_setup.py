from __future__ import annotations

import logging
import os
from pathlib import Path

import structlog

from fleetent.structured_logging import configure_structured_logging

_VALID_LOG_LEVELS = ("silent", "fatal", "error", "warn", "info", "debug", "trace")


def setup_process_logging(
    *,
    console_level: str = "info",
    file_level: str = "debug",
    directory: str | Path | None = None,
    log_format: str = "console",
) -> None:
    resolved_console_level = _resolve_console_level(console_level)
    configure_structured_logging(
        console_level=resolved_console_level,
        file_level=file_level,
        directory=directory,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        # NOTE (from feature/zhangyang Wave-1 fix): structlog.stdlib.add_logger_name
        # reads `logger.name`, which only exists on stdlib loggers — the PrintLogger
        # from PrintLoggerFactory below has none, so including it crashed every log
        # call at emit time. It is intentionally omitted.
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )


def _resolve_console_level(console_level: str) -> str:
    env_level = os.getenv("LOG_LEVEL")
    if env_level is None or env_level == "":
        return console_level
    if env_level not in _VALID_LOG_LEVELS:
        valid_levels = ", ".join(_VALID_LOG_LEVELS)
        raise ValueError(f"Invalid LOG_LEVEL {env_level!r}; valid values: {valid_levels}")
    return env_level
