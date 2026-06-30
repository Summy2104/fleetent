import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

import structlog
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from fleetent import paths
from fleetent.oidc_config import OidcSettings

PLATFORM_YAML_PATH = paths.platform_yaml_path()
# Empty after the config consolidation: the platform Settings carries no secret
# fields. Kept as a defensive safety net so the YAML source still refuses any known
# secret field, should one ever be reintroduced. Inline-secret scanning of agent.yaml
# now lives in platform/config_validation.py.
YAML_SECRET_FIELDS: frozenset[str] = frozenset()


class SecretRejectingYamlSettingsSource(YamlConfigSettingsSource):
    def __call__(self) -> dict[str, Any]:
        data = super().__call__()
        secret_fields = sorted(key for key in data if key in YAML_SECRET_FIELDS)
        if secret_fields:
            fields = ", ".join(secret_fields)
            raise ValueError(
                f"Secret fields cannot appear in platform.yaml: {fields}. "
                "Move these values to env/.env."
            )
        return data


class LoggingSettings(BaseModel):
    console_level: str = "info"
    file_level: str = "debug"
    # Blank means "resolve to agent home data/logs/"; explicit path used as-is.
    directory: str = ""
    json_file: bool = True


class ObservabilitySettings(BaseModel):
    logging: LoggingSettings = Field(default_factory=LoggingSettings)


class DiagnosticsRetentionSettings(BaseModel):
    enabled: bool = False
    logs_days: int | None = None
    traces_days: int | None = None
    diagnostic_exports_days: int | None = None


class DiagnosticsSettings(BaseModel):
    export_dir: str = Field(default_factory=lambda: str(paths.diagnostics_dir()))
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
    agent_memory_max_tokens: int = 512
    memory_top_k: int = 10
    knowledge_top_k: int = 10
    agent_memory_top_k: int = 5
    conflict_preference: Literal["auto", "memory", "knowledge", "agent_memory"] = "auto"
    # Per-retrieval-path timeout: a path exceeding this is degraded to empty so a
    # stalled external embedding proxy cannot block the whole build_context.
    retrieval_timeout_seconds: float = 5.0


class KnowledgeRetrievalAuditSettings(BaseModel):
    plaintext: bool = False


class KnowledgeBaseSettings(BaseModel):
    enabled: bool = False
    default_tenant_id: str = "default"
    default_kb_id: str = "global"
    chunk_size: int = 1_000
    chunk_overlap: int = 200
    retrieval_audit: KnowledgeRetrievalAuditSettings = Field(
        default_factory=KnowledgeRetrievalAuditSettings
    )
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


class McpApprovalRule(BaseModel):
    """One MCP approval rule (approval-boundary-redesign D4).

    Matches calls to ``tool`` (the server-local tool name). ``when`` is an optional
    arg-condition map (arg name → allowed values); a call matches when, for every listed
    arg, the call's value is in the list (AND across args). ``when=None`` matches the whole
    tool. A match raises the call to ``medium`` (approval); MCP calls otherwise default to
    no-approval.
    """

    tool: str
    when: dict[str, list[str]] | None = None


class McpOAuthSettings(BaseModel):
    """Self-hosted MCP OAuth2 (mcp-config-standardization / mcp-per-user-oauth2).

    ``token_url`` points at a customer-internal authorization server — never a cloud
    identity service. ``client_secret_env`` is the env var NAME, never the secret value.

    ``grant`` selects the OAuth2 grant: ``client_credentials`` (machine identity, the
    historical default) or ``authorization_code`` (per-user delegation). The
    authorization_code path additionally requires ``authorization_endpoint`` (where the
    user is sent to authorize) and ``redirect_path`` (the agent-hosted callback path); it
    is validated below so a misconfigured server fails loudly at load time.
    """

    type: str = "oauth2"
    grant: Literal["client_credentials", "authorization_code"] = "client_credentials"
    token_url: str = ""
    client_id: str = ""
    client_secret_env: str = ""
    scope: str = ""
    # authorization_code-only fields (ignored by client_credentials).
    authorization_endpoint: str = ""
    redirect_path: str = ""
    # stdio per-user oauth (mcp-per-user-oauth2 D4): env var name the user's access token is
    # injected under at subprocess spawn. Empty → the runtime default. http transports and
    # client_credentials ignore it.
    token_env: str = ""

    @model_validator(mode="after")
    def _require_authorization_code_fields(self) -> "McpOAuthSettings":
        """Reject an authorization_code grant that is missing fields it cannot run without.

        Validated against the user-delegation flow's hard prerequisites: the user must be
        sent to ``authorization_endpoint``, identified by ``client_id``, and the returned
        code exchanged at ``token_url``. ``client_credentials`` is unaffected.
        """
        if self.grant != "authorization_code":
            return self
        missing = [
            name
            for name in ("authorization_endpoint", "client_id", "token_url")
            if not getattr(self, name)
        ]
        if missing:
            raise ValueError("authorization_code grant requires non-empty " + ", ".join(missing))
        return self


class McpServerSettings(BaseModel):
    id: str
    transport: str = "http"
    url: str = ""
    auth_type: str = "none"
    api_key_env: str = ""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    # Custom HTTP headers for http transport, sent verbatim on every request.
    headers: dict[str, str] = Field(default_factory=dict)
    # Per-server HTTP timeouts in seconds (mcp-per-server-timeout).
    connect_timeout: float = 10.0
    call_timeout: float = 30.0
    # ── fleetent extensions (authored under the agent.yaml `x-fleetent` block) ──
    # Degradation policy when the server is unavailable: "degrade" | "strict" | "silent".
    degrade_mode: str = "degrade"
    # /exchange file-bridging for stdio products; `file_root` overrides the convention dir,
    # `file_isolation: "off"` opts the server out of the convention env injection.
    file_root: str = ""
    file_isolation: str = "on"
    # Self-hosted OAuth2 (None = header/api-key auth or no auth).
    auth: McpOAuthSettings | None = None
    # per-user dynamic api-key/bearer (mcp-per-user-apikey): server-level *method* settings;
    # the secret is per-user (supplied at runtime), never here. header_style decides injection
    # (Authorization: Bearer | X-API-Key); credential_input gates submission methods.
    header_style: str = "bearer"
    credential_input: str = "form"
    # Per-server approval rules (approval-boundary-redesign D4): which operations on this MCP
    # server require approval. Empty = all operations no-approval (the narrow-surface default).
    approval_rules: list[McpApprovalRule] = Field(default_factory=list)


_ENV_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_env_refs(value: Any) -> Any:
    """Expand ``${VAR}`` references against the process environment (recursive).

    Missing variables expand to the empty string. Matches the de-facto-standard config
    substitution used by other MCP clients; applied at load time.
    """
    if isinstance(value, str):
        return _ENV_REF_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, list):
        return [_expand_env_refs(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env_refs(v) for k, v in value.items()}
    return value


def parse_mcp_servers(raw: dict[str, Any], *, expand_env: bool = True) -> list[McpServerSettings]:
    """Parse the standard map-keyed MCP server config block into ``McpServerSettings``.

    Accepts the top-level ``mcpServers`` or ``mcp_servers`` key, where each entry is keyed
    by the server name (= ``id``). Transport is auto-detected (``command``→stdio,
    ``url``→remote) when unset; per-entry fleetent settings under ``x-fleetent`` are
    hoisted. The legacy ``list-of-id`` form is rejected.

    ``expand_env``: when True (standalone file load), ``${VAR}`` references are expanded
    at parse time. The AgentFile path passes ``False`` to keep references intact so the
    inline-secret guard sees the reference (not the resolved secret); the runtime resolves
    them at request time.
    """
    block = raw.get("mcpServers")
    if block is None:
        block = raw.get("mcp_servers")
    if block is None:
        return []
    if not isinstance(block, dict):
        raise ValueError(
            "MCP servers must be a map keyed by server name "
            "(legacy list-of-id form is not supported)"
        )
    servers: list[McpServerSettings] = []
    for name, body in block.items():
        if not isinstance(body, dict):
            raise ValueError(f"mcpServers[{name!r}] must be a mapping")
        body = _expand_env_refs(dict(body)) if expand_env else dict(body)
        ext = body.get("x-fleetent") or {}
        if not isinstance(ext, dict):
            raise ValueError(f"mcpServers[{name!r}].x-fleetent must be a mapping")
        raw_transport = body.get("type") or body.get("transport") or ""
        if raw_transport in ("", "remote", "http", "streamable-http", "sse"):
            transport = "stdio" if body.get("command") else "http"
        else:
            transport = str(raw_transport)
        auth_block = ext.get("auth")
        servers.append(
            McpServerSettings(
                id=str(name),
                transport=transport,
                url=body.get("url", ""),
                auth_type=body.get("auth_type", "none"),
                api_key_env=body.get("api_key_env", ""),
                command=body.get("command", ""),
                args=list(body.get("args", []) or []),
                env=dict(body.get("env", {}) or {}),
                headers=dict(body.get("headers", {}) or {}),
                connect_timeout=float(body.get("connect_timeout", 10.0)),
                call_timeout=float(body.get("call_timeout", 30.0)),
                degrade_mode=ext.get("degrade_mode", "degrade"),
                file_root=ext.get("file_root", ""),
                file_isolation=ext.get("file_isolation", "on"),
                auth=McpOAuthSettings(**auth_block) if isinstance(auth_block, dict) else None,
                approval_rules=[McpApprovalRule(**r) for r in (ext.get("approval_rules") or [])],
            )
        )
    return servers


class McpToolNamingTemplate(BaseModel):
    """Custom tool-name projection template (mcp-tool-name-projection).

    ``template`` uses ``{server}`` / ``{tool}`` placeholders; ``sanitize`` selects a
    character policy; ``max_len`` caps the projected name length.
    """

    model_config = ConfigDict(extra="forbid")

    template: str
    sanitize: str = "none"
    max_len: int = 64


class McpSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    # Tool-name projection target: a preset alias (claude|hermes|opencode|skills|bare)
    # or a custom template object. Default `claude` → mcp__{server}__{tool}.
    tool_naming: str | McpToolNamingTemplate = "claude"


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

    model_config = SettingsConfigDict(env_nested_delimiter="__", extra="ignore")

    log_format: str = "console"
    database_url: str = Field(default_factory=lambda: f"sqlite:///{paths.management_db_path()}")
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    oidc: OidcSettings = Field(default_factory=OidcSettings)

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
            settings_cls, yaml_file=PLATFORM_YAML_PATH
        )
        home_dotenv_settings = DotEnvSettingsSource(
            settings_cls,
            env_file=paths.platform_env_path(),
            env_nested_delimiter="__",
        )
        return (
            init_settings,
            env_settings,
            home_dotenv_settings,
            yaml_settings,
            file_secret_settings,
        )


def configure_logging(settings: Settings) -> None:
    from fleetent.structured_logging import configure_structured_logging

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
    """Parse MCP server definitions from an explicit YAML path.

    There is no default MCP config file in the MVP runtime. Platform-authored MCP
    definitions live in DB and are materialized into Agent ``agent.yaml``.
    """
    if path is None:
        return []
    config_path = path
    if not config_path.exists():
        return []

    raw = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ValueError("MCP server YAML must contain a mapping")
    return parse_mcp_servers(raw)
