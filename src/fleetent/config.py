import logging
from pathlib import Path
from typing import Any, Literal

import structlog
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from fleetent import paths

SETTINGS_YAML_PATH = paths.settings_yaml_path()
MCP_SERVERS_YAML_PATH = paths.config_dir() / "mcp.servers.yaml"
YAML_SECRET_FIELDS = frozenset(
    {
        "anthropic_api_key",
        "slack_bot_token",
        "slack_app_token",
        "telegram_bot_token",
    }
)


class SecretRejectingYamlSettingsSource(YamlConfigSettingsSource):
    def __call__(self) -> dict[str, Any]:
        data = super().__call__()
        secret_fields = sorted(key for key in data if key in YAML_SECRET_FIELDS)
        if secret_fields:
            fields = ", ".join(secret_fields)
            raise ValueError(
                f"Secret fields cannot appear in config/settings.yaml: {fields}. "
                "Move these values to env/.env."
            )
        return data


class LoggingSettings(BaseModel):
    console_level: str = "info"
    file_level: str = "debug"
    directory: str = Field(default_factory=lambda: str(paths.data_dir() / "logs"))
    json_file: bool = True


class ObservabilitySettings(BaseModel):
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


class DiagnosticsRetentionSettings(BaseModel):
    enabled: bool = False
    logs_days: int | None = None
    traces_days: int | None = None
    diagnostic_exports_days: int | None = None


class DiagnosticsSettings(BaseModel):
    export_dir: str = Field(default_factory=lambda: str(paths.data_dir() / "diagnostics"))
    retention: DiagnosticsRetentionSettings = Field(default_factory=DiagnosticsRetentionSettings)


class VectorStoreSettings(BaseModel):
    backend: str = "memory"
    database_url: str | None = None


class EmbeddingSettings(BaseModel):
    backend: str = "deterministic"
    dimensions: int = 64
    endpoint: str = ""
    model: str = ""
    api_key_env: str = ""
    timeout_seconds: float = 10.0


class RerankSettings(BaseModel):
    backend: str = "disabled"
    endpoint: str = ""
    model: str = ""
    api_key_env: str = ""
    timeout_seconds: float = 10.0


class LongTermContextSettings(BaseModel):
    max_tokens: int = 2_048
    memory_max_tokens: int = 1_024
    knowledge_max_tokens: int = 1_024
    memory_top_k: int = 10
    knowledge_top_k: int = 10
    conflict_preference: Literal["auto", "memory", "knowledge"] = "auto"


class KnowledgeBaseSettings(BaseModel):
    enabled: bool = False
    default_tenant_id: str = "default"
    default_kb_id: str = "global"
    chunk_size: int = 1_000
    chunk_overlap: int = 200
    google_drive: "GoogleDriveConnectorsSettings" = Field(
        default_factory=lambda: GoogleDriveConnectorsSettings()
    )
    confluence: "ConfluenceConnectorsSettings" = Field(
        default_factory=lambda: ConfluenceConnectorsSettings()
    )


class GoogleDriveConnectorSettings(BaseModel):
    connector_id: str
    tenant_id: str
    kb_id: str
    folder_id: str
    credential_ref: str = ""
    access_token_env: str = ""
    refresh_token_env: str = ""
    client_id_env: str = ""
    client_secret_env: str = ""
    token_uri_env: str = ""
    enabled: bool = True
    recursive: bool = True


class GoogleDriveConnectorsSettings(BaseModel):
    connectors: list[GoogleDriveConnectorSettings] = Field(default_factory=list)


class ConfluenceConnectorSettings(BaseModel):
    connector_id: str
    tenant_id: str
    kb_id: str
    base_url: str
    username: str = ""
    username_env: str = ""
    credential_ref: str = ""
    api_token_env: str = ""
    enabled: bool = True
    scope_type: Literal["space", "page"] | None = None
    space_key: str | None = None
    page_id: str | None = None
    include_children: bool = False

    @field_validator("page_id", mode="before")
    @classmethod
    def _normalize_page_id(cls, value: object) -> object:
        if isinstance(value, int):
            return str(value)
        return value


class ConfluenceConnectorsSettings(BaseModel):
    connectors: list[ConfluenceConnectorSettings] = Field(default_factory=list)


class McpServerSettings(BaseModel):
    id: str
    transport: str = "http"
    url: str = ""
    auth_type: str = "none"
    api_key_env: str = ""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class McpServersFile(BaseModel):
    servers: list[McpServerSettings] = Field(default_factory=list)


class McpSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True


class SchedulingSettings(BaseModel):
    enabled: bool = True
    default_timezone: str = "UTC"


class WebhooksSettings(BaseModel):
    enabled: bool = True
    max_body_bytes: int = 1_048_576


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")

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
    database_url: str = Field(
        default_factory=lambda: f"sqlite:///{paths.data_dir() / 'fleetent.db'}"
    )
    # ── runtime tuning fields merged from feature/zhangyang (flat, per D1) ──
    # Compression dual-threshold (AR12) + layered retention (AR13) + anti-flap (AR17).
    context_tmax_ratio: float = 0.8
    context_tretained_ratio: float = 0.6
    compression_initial_intent_max: int = 2
    context_flap_window: int = 3
    context_min_savings_ratio: float = 0.10
    context_min_interval_turns: int = 1
    # Cross-run layered budget caps (AR18). -1 = unlimited (backward-compatible).
    agent_budget_session_turns: int = -1
    agent_budget_session_tokens: int = -1
    agent_budget_user_turns: int = -1
    agent_budget_user_tokens: int = -1
    agent_budget_agent_turns: int = -1
    agent_budget_agent_tokens: int = -1
    agent_budget_global_turns: int = -1
    agent_budget_global_tokens: int = -1
    agent_budget_user_window: str = "weekly"
    agent_budget_agent_window: str = "weekly"
    agent_budget_global_window: str = "monthly"
    # Session disk management (S1/S2/S4) + internal maintenance loop.
    session_ttl_days: int = 30
    session_max_total_mb: int = 1024
    session_max_count: int = 10000
    session_cleanup_interval_seconds: float = 3600.0
    # Agent loop / budget / loop-detection / guardrails (AR2/AR4/AR10/AR20/T2/AR3).
    agent_max_turns: int = 50
    agent_max_consecutive_failures: int = 3
    sub_agent_timeout_seconds: int = 300
    tool_default_timeout_seconds: float = 30.0
    agent_max_tokens: int = -1
    agent_grace_call_token_ratio: float = 0.05
    agent_grace_call_min_tokens: int = 512
    agent_loop_repeat_threshold: int = 3
    guardrail_repeat_threshold: int = 3
    agent_tool_parallel_max: int = 8
    loop_detect_ignore_arg_keys: list[str] = []
    # Provider health circuit breaker (MR3, model_router fallback).
    provider_failure_threshold: int = 3
    provider_cooldown_seconds: int = 60
    # Skill disable list + self-hosted image/vision endpoints (data-sovereignty).
    disabled_skills: list[str] = []
    image_gen_url: str = ""
    image_gen_model: str = "default"
    vision_url: str = ""
    vision_model: str = "default"
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    diagnostics: DiagnosticsSettings = Field(default_factory=DiagnosticsSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    rerank: RerankSettings = Field(default_factory=RerankSettings)
    long_term_ctx: LongTermContextSettings = Field(default_factory=LongTermContextSettings)
    knowledge_base: KnowledgeBaseSettings = Field(default_factory=KnowledgeBaseSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)
    scheduling: SchedulingSettings = Field(default_factory=SchedulingSettings)
    webhooks: WebhooksSettings = Field(default_factory=WebhooksSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_settings = SecretRejectingYamlSettingsSource(
            settings_cls, yaml_file=SETTINGS_YAML_PATH
        )
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            yaml_settings,
            file_secret_settings,
        )


def configure_logging(settings: Settings) -> None:
    from fleetent.observability.structured_logging import configure_structured_logging

    configure_structured_logging(
        console_level=settings.observability.logging.console_level,
        file_level=settings.observability.logging.file_level,
        directory=settings.observability.logging.directory,
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


def load_mcp_server_settings(
    path: Path | None = None,
) -> list[McpServerSettings]:
    """Load static MCP server definitions from the dedicated server config file."""
    config_path = path or MCP_SERVERS_YAML_PATH
    if not config_path.exists():
        return []

    raw = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError("config/mcp.servers.yaml must contain a mapping with a servers list")
    return McpServersFile.model_validate(raw).servers
