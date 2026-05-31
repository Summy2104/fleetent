import logging

import structlog
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingSettings(BaseModel):
    console_level: str = "info"
    file_level: str = "debug"
    directory: str = "data/logs"
    json_file: bool = True


class ObservabilitySettings(BaseModel):
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    slack_bot_token: str = ""
    slack_app_token: str = ""
    telegram_bot_token: str = ""
    microsandbox_url: str = "http://host.docker.internal:7777"
    permission_gate_medium_timeout_seconds: int = 300
    permission_gate_high_timeout_seconds: int = 3600
    context_max_tokens: int = 200_000
    context_compress_threshold: float = 0.8
    context_keep_recent: int = 10
    log_format: str = "console"
    default_agent_name: str | None = None
    database_url: str = "sqlite:///data/users.db"
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)


def configure_logging(settings: Settings) -> None:
    from fleetent.observability.structured_logging import configure_structured_logging

    configure_structured_logging(
        console_level=settings.observability.logging.console_level,
        file_level=settings.observability.logging.file_level,
        directory=settings.observability.logging.directory,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
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
