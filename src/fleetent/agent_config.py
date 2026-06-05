"""File-driven agent configuration: self-contained `agent.yaml` per agent.

Each agent lives at ``<agents_dir>/<name>/agent.yaml`` and fully describes the agent
(definition, capability switches, inline MCP servers, and channel/user bindings). This
module parses and validates those files and builds the in-memory index the runtime
uses to resolve agents and route requests — with zero database access. The DB and
admin console remain the authoring source of truth; these files are generated artifacts
(see openspec change ``file-driven-agent-config``).
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fleetent import paths
from fleetent.config import (
    DiagnosticsSettings,
    EmbeddingSettings,
    KnowledgeBaseSettings,
    LongTermContextSettings,
    McpServerSettings,
    McpSettings,
    ObservabilitySettings,
    RerankSettings,
    SchedulingSettings,
    VectorStoreSettings,
    WebhooksSettings,
)
from fleetent.platform.config_validation import _flatten, _looks_inline_secret

# Agents root directory. Module-level constant (injectable via monkeypatch per the
# project's no-global-mutable-state rule); env override mirrors FLEETENT_SKILLS_DIR.
AGENTS_DIR = paths.config_dir() / "agents"

AGENT_FILE_NAME = "agent.yaml"
_ENV_VAR_NAME_RE = re.compile(r"^(env:)?[A-Z_][A-Z0-9_]*$")


class AgentBindings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: bool = False
    channels: list[str] = Field(default_factory=list)
    users: list[str] = Field(default_factory=list)


class SlackConnector(BaseModel):
    """Per-agent Slack connection. Tokens are env-var names, never inline secrets."""

    model_config = ConfigDict(extra="forbid")

    bot_token_env: str
    app_token_env: str
    # Optional channel filter: when non-empty, the agent responds only in these channels
    # among those its Slack app receives events from. Empty = respond everywhere.
    channels: list[str] = Field(default_factory=list)


class AgentConnectors(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slack: SlackConnector | None = None


class AgentAccess(BaseModel):
    """Per-agent IM access rules, read from the agent home (no platform-DB lookup).

    The default is closed: with no rules an agent grants no implicit access and
    requires approval, rather than the legacy allowlist-off = allow-all behaviour.
    """

    model_config = ConfigDict(extra="forbid")

    # Empty allow_channels = allow all channels the agent is bound to.
    allow_channels: list[str] = Field(default_factory=list)
    allow_users: list[str] = Field(default_factory=list)
    require_approval: bool = True


class ModelTarget(BaseModel):
    """Agent-local model endpoint definition."""

    model_config = ConfigDict(extra="forbid")

    id: str
    provider: str
    protocol: str
    base_url: str | None = None
    endpoint: str | None = None
    model: str | None = None
    api_key_env: str | None = None
    max_tokens: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_protocol_requirements(self) -> "ModelTarget":
        if not self.id.strip():
            raise ValueError("model target id must not be empty")
        if not self.provider.strip():
            raise ValueError(f"model target '{self.id}' provider must not be empty")
        if not self.protocol.strip():
            raise ValueError(f"model target '{self.id}' protocol must not be empty")
        if self.protocol == "openai_chat" and (not self.base_url or not self.model):
            raise ValueError(f"model target '{self.id}' requires base_url and model")
        if self.protocol == "openai_image_generation" and (not self.endpoint or not self.model):
            raise ValueError(f"model target '{self.id}' requires endpoint and model")
        if self.protocol in {"http_embedding", "http_rerank"} and not self.endpoint:
            raise ValueError(f"model target '{self.id}' requires endpoint")
        return self


class ModelRouteEntry(BaseModel):
    """One route entry, ordered by fallback priority."""

    model_config = ConfigDict(extra="forbid")

    target: str
    max_tokens: int | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class AgentModels(BaseModel):
    """Agent-local model policy section."""

    model_config = ConfigDict(extra="forbid")

    targets: list[ModelTarget]
    routes: dict[str, list[ModelRouteEntry]]

    @model_validator(mode="after")
    def _validate_targets_and_routes(self) -> "AgentModels":
        target_ids: set[str] = set()
        for target in self.targets:
            if target.id in target_ids:
                raise ValueError(f"duplicate target id '{target.id}'")
            target_ids.add(target.id)
        for route, entries in self.routes.items():
            if not route.strip():
                raise ValueError("model route key must not be empty")
            if not entries:
                raise ValueError(f"model route '{route}' must contain at least one target")
            for entry in entries:
                if entry.target not in target_ids:
                    raise ValueError(
                        f"model route '{route}' references unknown model target '{entry.target}'"
                    )
        return self


class AgentFile(BaseModel):
    """Schema for a self-contained ``agent.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: int
    tenant_id: str = "default"
    team_id: str | None = None
    system_prompt: str = ""
    models: AgentModels
    memory_namespace: str = ""
    skills_dir: str | None = None
    allowed_skills: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)
    mcp_servers: list[McpServerSettings] = Field(default_factory=list)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    rerank: RerankSettings = Field(default_factory=RerankSettings)
    knowledge_base: KnowledgeBaseSettings = Field(default_factory=KnowledgeBaseSettings)
    long_term_ctx: LongTermContextSettings = Field(default_factory=LongTermContextSettings)
    # ── per-agent runtime governance (defaults mirror Settings; schema-only this phase,
    #    runtime wiring lands in runtime-read-agent-config) ──
    # context compression
    context_max_tokens: int = 200_000
    context_compress_threshold: float = 0.8
    context_keep_recent: int = 10
    context_tmax_ratio: float = 0.8
    context_tretained_ratio: float = 0.6
    compression_initial_intent_max: int = 2
    context_flap_window: int = 3
    context_min_savings_ratio: float = 0.10
    context_min_interval_turns: int = 1
    # layered budget — session/user/agent dims only (global dropped: no cross-agent runtime)
    agent_budget_session_turns: int = -1
    agent_budget_session_tokens: int = -1
    agent_budget_user_turns: int = -1
    agent_budget_user_tokens: int = -1
    agent_budget_agent_turns: int = -1
    agent_budget_agent_tokens: int = -1
    agent_budget_user_window: str = "weekly"
    agent_budget_agent_window: str = "weekly"
    # loop / budget / guardrail
    agent_max_turns: int = 50
    agent_max_consecutive_failures: int = 3
    agent_max_tokens: int = -1
    agent_grace_call_token_ratio: float = 0.05
    agent_grace_call_min_tokens: int = 512
    agent_loop_repeat_threshold: int = 3
    guardrail_repeat_threshold: int = 3
    agent_tool_parallel_max: int = 8
    loop_detect_ignore_arg_keys: list[str] = Field(default_factory=list)
    sub_agent_timeout_seconds: int = 300
    tool_default_timeout_seconds: float = 30.0
    # permission gate
    permission_gate_medium_timeout_seconds: int = 300
    permission_gate_high_timeout_seconds: int = 3600
    # provider circuit breaker
    provider_failure_threshold: int = 3
    provider_cooldown_seconds: int = 60
    # ── per-agent deployment / process knobs (defaults mirror Settings) ──
    microsandbox_url: str = "http://host.docker.internal:7777"
    log_format: str = "console"
    session_ttl_days: int = 30
    session_max_total_mb: int = 1024
    session_max_count: int = 10000
    session_cleanup_interval_seconds: float = 3600.0
    image_gen_url: str = ""
    image_gen_model: str = "default"
    vision_url: str = ""
    vision_model: str = "default"
    disabled_skills: list[str] = Field(default_factory=list)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    diagnostics: DiagnosticsSettings = Field(default_factory=DiagnosticsSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)
    scheduling: SchedulingSettings = Field(default_factory=SchedulingSettings)
    webhooks: WebhooksSettings = Field(default_factory=WebhooksSettings)
    connectors: AgentConnectors = Field(default_factory=AgentConnectors)
    bindings: AgentBindings = Field(default_factory=AgentBindings)
    access: AgentAccess = Field(default_factory=AgentAccess)


@dataclass(frozen=True)
class AgentConfigIndex:
    """In-memory resolution index built from scanning the agents directory."""

    agents: dict[str, AgentFile]
    by_channel: dict[str, str]
    by_user: dict[str, str]
    default: str | None

    def get(self, name: str) -> AgentFile | None:
        return self.agents.get(name)

    def agent_for_channel(self, platform: str, channel_id: str) -> str | None:
        return self.by_channel.get(f"{platform}:{channel_id}")

    def agent_for_user(self, user_id: str) -> str | None:
        return self.by_user.get(user_id)

    def default_agent(self) -> str | None:
        return self.default

    def slack_agents(self) -> list[str]:
        """Names of agents that declare a Slack connector."""
        return [name for name, a in self.agents.items() if a.connectors.slack is not None]


# Current published index. Empty until scan() runs (mirrors skill_registry._index).
_index = AgentConfigIndex(agents={}, by_channel={}, by_user={}, default=None)


def _resolve_agents_dir(agents_dir: str | Path | None) -> Path:
    """Return the agents root, falling back to env then the default."""
    if agents_dir is not None:
        return Path(agents_dir)
    return Path(os.environ.get("FLEETENT_AGENTS_DIR", str(AGENTS_DIR)))


def load_agent_file(agent_dir: Path) -> AgentFile:
    """Parse ``<agent_dir>/agent.yaml`` and validate the directory name matches ``name``."""
    path = agent_dir / AGENT_FILE_NAME
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping")
    agent = AgentFile.model_validate(raw)
    if agent.name != agent_dir.name:
        raise ValueError(
            f"agent directory '{agent_dir.name}' does not match in-file name "
            f"'{agent.name}' ({path})"
        )
    _reject_inline_secrets(agent, path)
    return agent


def _reject_inline_secrets(agent: AgentFile, path: Path) -> None:
    """Reject inline plaintext secrets in MCP/connector defs; secrets go via env refs."""
    payload = {
        "mcp_servers": [server.model_dump() for server in agent.mcp_servers],
        "connectors": agent.connectors.model_dump(),
    }
    intelligence_payload = {
        "models": agent.models.model_dump(),
        "embedding": agent.embedding.model_dump(),
        "rerank": agent.rerank.model_dump(),
        "knowledge_base": agent.knowledge_base.model_dump(),
    }
    for key, value in _flatten(payload):
        if (
            isinstance(value, str)
            and _looks_inline_secret(value)
            and not _is_env_reference(key, value)
        ):
            raise ValueError(
                f"inline secret-like value in agent '{agent.name}' at '{key}' ({path}); "
                "reference secrets by environment-variable name instead"
            )
    for key, value in _flatten(intelligence_payload):
        if not _is_secret_reference_key(key) or not isinstance(value, str):
            continue
        if _looks_inline_secret(value) and not _is_env_reference(key, value):
            raise ValueError(
                f"inline secret-like value in agent '{agent.name}' at '{key}' ({path}); "
                "reference secrets by environment-variable name instead"
            )


def _is_env_reference(key: str, value: str) -> bool:
    if key.endswith("_env"):
        return _ENV_VAR_NAME_RE.fullmatch(value) is not None
    if key.endswith("credential_ref"):
        return _ENV_VAR_NAME_RE.fullmatch(value) is not None or value.startswith("file://")
    return False


def _is_secret_reference_key(key: str) -> bool:
    return key.endswith("_env") or key.endswith("credential_ref")


def load_agent_home_file(path: Path) -> AgentFile:
    """Parse the single-agent ``agent.yaml``.

    Unlike :func:`load_agent_file`, this skips the directory-name check — the config-dir
    single-agent file has no ``<name>/`` parent. Inline-secret rejection still applies.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping")
    agent = AgentFile.model_validate(raw)
    _reject_inline_secrets(agent, path)
    return agent


def _single_agent_index(agent: AgentFile) -> AgentConfigIndex:
    """Build an index from one single-file agent: it is the sole, forced-default agent."""
    by_channel = {ch: agent.name for ch in agent.bindings.channels}
    by_user = {u: agent.name for u in agent.bindings.users}
    return AgentConfigIndex(
        agents={agent.name: agent}, by_channel=by_channel, by_user=by_user, default=agent.name
    )


def build_index(agents_dir: str | Path | None = None) -> AgentConfigIndex:
    """Build a fresh resolution index (pure; no globals).

    Single-file mode: when no explicit ``agents_dir`` / ``FLEETENT_AGENTS_DIR`` is given
    and a home-root ``agent.yaml`` exists, load it as the sole, forced-default agent.
    Otherwise scan the agents directory (multi-agent).
    """
    if agents_dir is None and "FLEETENT_AGENTS_DIR" not in os.environ:
        home_file = paths.agent_file()
        if home_file.is_file():
            return _single_agent_index(load_agent_home_file(home_file))

    root = _resolve_agents_dir(agents_dir)
    agents: dict[str, AgentFile] = {}
    by_channel: dict[str, str] = {}
    by_user: dict[str, str] = {}
    default: str | None = None

    if root.is_dir():
        for agent_dir in sorted(p for p in root.iterdir() if (p / AGENT_FILE_NAME).is_file()):
            agent = load_agent_file(agent_dir)
            agents[agent.name] = agent
            for channel in agent.bindings.channels:
                if channel in by_channel:
                    raise ValueError(
                        f"channel '{channel}' is bound by both '{by_channel[channel]}' "
                        f"and '{agent.name}'"
                    )
                by_channel[channel] = agent.name
            for user in agent.bindings.users:
                if user in by_user:
                    raise ValueError(
                        f"user '{user}' is bound by both '{by_user[user]}' and '{agent.name}'"
                    )
                by_user[user] = agent.name
            if agent.bindings.default:
                if default is not None:
                    raise ValueError(
                        f"multiple default agents declared: '{default}' and '{agent.name}'"
                    )
                default = agent.name

    return AgentConfigIndex(agents=agents, by_channel=by_channel, by_user=by_user, default=default)


def scan(agents_dir: str | Path | None = None) -> None:
    """Rebuild and publish the current index. Server runs once at startup; CLI per call."""
    global _index
    _index = build_index(agents_dir)


def scan_home(agent_dir: str | Path) -> AgentFile:
    """Publish a single-agent index from one agent home dir (standalone runtime).

    Loads ``<agent_dir>/agent.yaml`` (dir name must match the agent name) and publishes
    it as the sole, forced-default agent. Used by ``fleetent agent run`` so routing
    resolves only this one self-contained agent.
    """
    global _index
    agent = load_agent_file(Path(agent_dir))
    _index = _single_agent_index(agent)
    return agent


def current() -> AgentConfigIndex:
    """Return the currently published index."""
    return _index


def active_agent() -> AgentFile | None:
    """The single active agent for this process, or None.

    A standalone ``fleetent agent run`` process publishes exactly one (forced-default)
    agent, so process-level config (intelligence backends, deployment knobs) resolves
    from it. In the multi-agent dev/platform index (or an empty one) this returns None
    and callers fall back to ``active_agent_or_default``'s neutral default.
    """
    if len(_index.agents) == 1:
        return next(iter(_index.agents.values()))
    return None


def default_models() -> AgentModels:
    """Return a local no-auth model policy for neutral in-process defaults."""
    return AgentModels(
        targets=[
            ModelTarget(
                id="default",
                provider="local",
                protocol="openai_chat",
                base_url="http://localhost:11434/v1/",
                model="default",
                max_tokens=4096,
            ),
            ModelTarget(
                id="vision",
                provider="local",
                protocol="openai_chat",
                base_url="http://localhost:11434/v1/",
                model="default-vision",
                max_tokens=4096,
            ),
            ModelTarget(
                id="embedding",
                provider="local",
                protocol="http_embedding",
                endpoint="http://localhost:11434/v1/embeddings",
                model="default-embedding",
                params={"dimensions": 64},
            ),
        ],
        routes={
            "default": [ModelRouteEntry(target="default")],
            "memory_extraction": [ModelRouteEntry(target="default")],
            "vision": [ModelRouteEntry(target="vision")],
            "embedding": [ModelRouteEntry(target="embedding")],
        },
    )


# Neutral default carrying the schema's literal defaults. It is the process-level
# fallback source for runtime knobs (intelligence/deployment/session) when no single
# agent is deployed (multi-agent dev/platform/empty index) — replacing the historical
# global ``Settings`` fallback after the config consolidation.
_DEFAULT_AGENT_FILE = AgentFile(name="", version=0, models=default_models())


def active_agent_or_default() -> AgentFile:
    """The single active agent for this process, or a neutral default with schema defaults."""
    return active_agent() or _DEFAULT_AGENT_FILE
