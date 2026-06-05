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
    dimensions_env: str = ""
    endpoint: str = ""
    endpoint_env: str = ""
    model: str = ""
    model_env: str = ""
    api_key_env: str = ""
    timeout_seconds: float = 10.0


class RerankSettings(BaseModel):
    backend: str = "disabled"
    endpoint: str = ""
    endpoint_env: str = ""
    model: str = ""
    model_env: str = ""
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
    """Slim platform control-plane settings.

    Agent-runtime configuration (governance / deployment / intelligence namespaces)
    was consolidated into the per-agent ``agent.yaml`` (dissolve-global-settings); this
    surface keeps only the platform authoring/control-plane DB and the platform process
    logging. Secrets stay in env. Intelligence sub-model classes above remain in this
    module purely so ``AgentFile`` can reuse them.
    """

    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")

    anthropic_api_key: str
    slack_bot_token: str = ""
    slack_app_token: str = ""
    telegram_bot_token: str = ""
    log_format: str = "console"
    default_agent_name: str | None = None
    database_url: str = Field(
        default_factory=lambda: f"sqlite:///{paths.data_dir() / 'fleetent.db'}"
    )
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

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
