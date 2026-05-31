import logging

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    slack_bot_token: str = ""
    slack_app_token: str = ""
    telegram_bot_token: str = ""
    permission_gate_medium_timeout_seconds: int = 300
    permission_gate_high_timeout_seconds: int = 3600
    context_max_tokens: int = 200_000
    context_tmax_ratio: float = 0.8
    context_tretained_ratio: float = 0.6
    context_keep_recent: int = 10
    session_ttl_days: int = 30
    session_max_total_mb: int = 1024
    session_max_count: int = 10000
    # How often the internal save()-triggered maintenance may run a full cleanup
    # scan (seconds). Time-gated so the rglob stays cheap under message volume.
    session_cleanup_interval_seconds: float = 3600.0
    agent_max_turns: int = 50
    agent_max_consecutive_failures: int = 3
    provider_failure_threshold: int = 3
    provider_cooldown_seconds: int = 60
    log_format: str = "console"
    default_agent_name: str | None = None
    disabled_skills: list[str] = []
    # Self-hosted, OpenAI-compatible images endpoint (e.g. SD-WebUI / ComfyUI /
    # Flux behind a compat layer). Empty = unconfigured; the generate_image tool
    # returns an explicit failure rather than silently succeeding. Cloud-hosted
    # proprietary services (DALL·E / Midjourney) are forbidden by data sovereignty.
    image_gen_url: str = ""
    image_gen_model: str = "default"


def configure_logging(settings: Settings) -> None:
    # NOTE: structlog.stdlib.add_logger_name reads `logger.name`, which only exists
    # on stdlib loggers — the PrintLogger from PrintLoggerFactory below has none, so
    # including it crashed every log call at emit time. It is intentionally omitted.
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.log_format == "json":
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
