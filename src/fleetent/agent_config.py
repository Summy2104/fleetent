"""File-driven agent configuration: self-contained `agent.yaml` per agent.

Each agent lives at ``<agents_dir>/<name>/agent.yaml`` and fully describes the agent
(definition, capability switches, inline MCP servers, and per-platform IM access rules).
This module parses and validates those files and builds the in-memory index the runtime
uses to resolve agents — with zero database access. The DB and admin console remain the
authoring source of truth; these files are generated artifacts
(see openspec change ``file-driven-agent-config``).
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fleetent import paths
from fleetent.config import (
    DiagnosticsSettings,
    EmbeddingSettings,
    LongTermContextSettings,
    McpServerSettings,
    McpSettings,
    ObservabilitySettings,
    RerankSettings,
    SchedulingSettings,
    VectorStoreSettings,
    WebhooksSettings,
)
from fleetent.secret_scan import flatten, looks_inline_secret

# Agents root directory. Module-level constant (injectable via monkeypatch per the
# project's no-global-mutable-state rule); env override mirrors FLEETENT_SKILLS_DIR.
AGENTS_DIR = paths.agents_dir()

AGENT_FILE_NAME = "agent.yaml"
_ENV_VAR_NAME_RE = re.compile(r"^(env:)?[A-Z_][A-Z0-9_]*$")
_IGNORED_LEGACY_GOVERNANCE_KEYS = frozenset(
    {
        f"{'_'.join(('agent', 'budget', 'session'))}_turns",
        f"{'_'.join(('agent', 'budget', 'session'))}_tokens",
        f"{'_'.join(('agent', 'budget', 'user'))}_turns",
        f"{'_'.join(('agent', 'budget', 'user'))}_tokens",
        f"{'_'.join(('agent', 'budget', 'agent'))}_turns",
        f"{'_'.join(('agent', 'budget', 'agent'))}_tokens",
        f"{'_'.join(('agent', 'budget', 'user'))}_window",
        f"{'_'.join(('agent', 'budget', 'agent'))}_window",
    }
)


class ApprovalEntry(BaseModel):
    """One approval routing entry: a list of approver addresses and the quorum policy."""

    model_config = ConfigDict(extra="forbid")

    approvers: list[str] = Field(default_factory=list)
    policy: Literal["any", "all"] = "any"


# Sentinel approver address: route the approval prompt back to the requesting
# conversation (reply_func) instead of an outbound DM. Reserved as a platform name.
REQUESTER_SENTINEL = "requester"


class ApprovalRiskRoutes(BaseModel):
    """Per-risk-level approval routing."""

    model_config = ConfigDict(extra="forbid")

    medium: ApprovalEntry | None = None
    high: ApprovalEntry | None = None


class ApprovalRouting(BaseModel):
    """Agent-level approval routing configuration.

    Approver addresses are opaque strings in ``platform:target_id`` format
    (e.g. ``slack:UXXXXXXXX``, ``telegram:123456789``).
    ``by_tool`` takes precedence over ``by_risk`` when both match a tool call.
    """

    model_config = ConfigDict(extra="forbid")

    on_no_approver: Literal["reject"] = "reject"
    by_risk: ApprovalRiskRoutes = Field(default_factory=ApprovalRiskRoutes)
    by_tool: dict[str, ApprovalEntry] = Field(default_factory=dict)


class ImAccess(BaseModel):
    """Per-platform IM access rules, embedded in each IM binding declaration.

    The default is closed: with no rules the agent grants no implicit access and
    requires approval. Empty allow_groups = allow all groups the binding receives
    events from.
    """

    model_config = ConfigDict(extra="forbid")

    allow_groups: list[str] = Field(default_factory=list)
    allow_users: list[str] = Field(default_factory=list)
    # When true, skip the user gate entirely — all users are allowed on this binding.
    # Intended for open internal bots; does not affect group gate.
    allow_all_users: bool = False
    require_approval: bool = True


class SlackBinding(BaseModel):
    """Per-agent Slack connection. Tokens are env-var names, never inline secrets."""

    model_config = ConfigDict(extra="forbid")

    bot_token_env: str
    app_token_env: str
    access: ImAccess = Field(default_factory=ImAccess)


class TelegramBinding(BaseModel):
    """Per-agent Telegram connection. The token is an env-var name, never an inline secret."""

    model_config = ConfigDict(extra="forbid")

    bot_token_env: str
    access: ImAccess = Field(default_factory=ImAccess)


class ImBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supports_dm: bool = False
    supports_groups: bool = False
    slack: SlackBinding | None = None
    telegram: TelegramBinding | None = None


class AgentBindings(BaseModel):
    """Optional top-level runtime bindings materialized by the control plane."""

    model_config = ConfigDict(extra="forbid")

    default: bool = False
    users: list[str] = Field(default_factory=list)


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
        if self.protocol == "openai_image_chat" and (not self.base_url or not self.model):
            raise ValueError(f"model target '{self.id}' requires base_url and model")
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


class AgentKnowledgePermissions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search: bool = True


class AgentKnowledgeBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    kb_id: str
    default: bool = False
    permissions: AgentKnowledgePermissions = Field(default_factory=AgentKnowledgePermissions)


class AgentRetrievalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    top_k: int = 10
    rerank: bool = False
    embedding_route: str = ""
    rerank_route: str = ""


class AgentKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    bindings: list[AgentKnowledgeBinding] = Field(default_factory=list)
    retrieval_policy: AgentRetrievalPolicy = Field(default_factory=AgentRetrievalPolicy)

    @model_validator(mode="after")
    def _validate_bindings(self) -> "AgentKnowledge":
        if self.enabled and not self.bindings:
            raise ValueError("knowledge.bindings must contain at least one binding when enabled")
        defaults = [binding for binding in self.bindings if binding.default]
        if len(defaults) > 1:
            raise ValueError("knowledge.bindings may mark at most one default binding")
        return self


class SandboxMicrosandboxSettings(BaseModel):
    """Per-agent microsandbox backend options (sandbox-backend-abstraction)."""

    model_config = ConfigDict(extra="forbid")

    image: str | None = None


class SandboxDockerSettings(BaseModel):
    """Per-agent Docker backend options (sandbox-image-config).

    ``image`` overrides the Docker sandbox base image for this agent (e.g. a
    ``fleetent-sandbox`` image with file-operation libs baked in so run_code can produce
    xlsx/docx/pdf offline). ``None`` inherits the platform default / built-in
    ``python:3.12-slim``."""

    model_config = ConfigDict(extra="forbid")

    image: str | None = None


class SandboxSkillMountSettings(BaseModel):
    """Per-agent skills-mount options (sandbox-skill-mount).

    `enabled` toggles bind-mounting the host skills root into `/workspace/skills`;
    `read_only` mounts it ro (default) so the agent cannot rewrite skill assets;
    `source` optionally overrides the resolved effective skills root (``None`` →
    the registry's resolved user root).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    read_only: bool = True
    source: str | None = None


class SandboxResourcesSettings(BaseModel):
    """Per-agent sandbox container resource + hardening profile (per-agent-sandbox-resources).

    Mirrors `integrations.sandbox.config.SandboxResources`; every field is optional and
    `None` means "inherit the code-level safe default" — the manager builds a concrete
    `SandboxResources` by laying declared fields over `SandboxResources()` (with the same
    value-level validation/clamp/enum-fallback as before). Replaces the machine-shared
    `platform.yaml` `sandbox.resources` + `sandbox.agent_scope` (collapsed to one tier).
    Value-level invalid inputs (e.g. `memory=0`, unknown `network`) are not rejected here;
    they fall back to the field default with a warning at build time.
    """

    model_config = ConfigDict(extra="forbid")

    memory: int | None = None
    cpus: float | None = None
    network: str | None = None
    exec_timeout: int | None = None
    read_only: bool | None = None
    memory_swap_mb: int | None = None
    pids_limit: int | None = None
    tmpfs_size_mb: int | None = None
    cap_drop_all: bool | None = None
    cap_add: list[str] | None = None
    no_new_privileges: bool | None = None
    init: bool | None = None
    run_as_user: str | None = None


class SandboxSettings(BaseModel):
    """Per-agent sandbox backend selection (sandbox-backend-abstraction).

    `backend` (``docker`` | ``microsandbox``) overrides the platform default for this
    agent; ``None`` inherits the platform-level `sandbox.backend`. An invalid value is
    not rejected here — the factory warns and falls back to docker — so a typo never
    blocks the agent from loading. `skill_mount` (sandbox-skill-mount) configures the
    host skills bind-mount into `/workspace/skills`.

    `image_persistence` + `setup_command` (sandbox-image-persistence) are the
    *independent* per-agent dependency-image switch, orthogonal to `workspace_scope`
    (data isolation). When enabled on a `persist_workspace` backend, `setup_command` is
    baked offline into an immutable deps image that runtime containers boot read-only
    from. Both default off/empty so unspecified agents behave exactly as before; this
    is schema-only validation (the manager/backend act on it).

    `multi_user` (sandbox-multi-user-default) is the run-shape signal driving the
    workspace-scope guard; **default True (fail-safe)** — every agent is treated as
    multi-user (per-user session isolation enforced), and a single-user deployment that
    wants agent-scope cross-session data reuse must opt out with `multi_user: false`.
    """

    model_config = ConfigDict(extra="forbid")

    backend: str | None = None
    microsandbox: SandboxMicrosandboxSettings = Field(default_factory=SandboxMicrosandboxSettings)
    docker: SandboxDockerSettings = Field(default_factory=SandboxDockerSettings)
    skill_mount: SandboxSkillMountSettings = Field(default_factory=SandboxSkillMountSettings)
    image_persistence: bool = False
    setup_command: str | None = None
    # Per-agent sandbox resource/hardening profile + lifecycle (per-agent-sandbox-resources).
    # `resources` replaces the machine-shared platform.yaml `sandbox.resources`/`agent_scope`;
    # `workspace_scope` ("session"|"agent", None → code default "session") and `idle_hours`
    # (None → code default) move off platform.yaml's lifecycle section onto each agent.
    resources: SandboxResourcesSettings = Field(default_factory=SandboxResourcesSettings)
    workspace_scope: str | None = None
    idle_hours: float | None = None
    # Multi-user run-shape signal (sandbox-multi-user-default). Fail-safe default True:
    # every agent is treated as multi-user, so the manager's guard corrects a configured
    # `agent` workspace_scope to `session` (per-user isolation) unless a single-user
    # deployment explicitly opts out with `multi_user: false`. Carried via config (not
    # runtime inference) to keep the agent runtime free of platform-topology knowledge.
    multi_user: bool = True


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
    # agent-skill-tools: gate for the model-facing skill_manage authoring tool.
    # Default off — skill_manage only enters this agent's tool schema when explicitly
    # enabled, so a deployment opts into agent-driven skill writes deliberately.
    skill_authoring_enabled: bool = False
    allowed_tools: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)
    mcp_servers: list[McpServerSettings] = Field(default_factory=list)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    rerank: RerankSettings = Field(default_factory=RerankSettings)
    knowledge: AgentKnowledge = Field(default_factory=AgentKnowledge)
    long_term_ctx: LongTermContextSettings = Field(default_factory=LongTermContextSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
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
    # run-time input steering (C1)
    steering_mode: Literal["steer", "queue", "interrupt"] = "steer"
    steering_max_pending: int = 8
    # hooks extension system (P1)
    hooks_enabled: bool = False
    hooks_decision_failure: Literal["open", "strict"] = "open"
    hooks_timeout_seconds: float = 5.0
    # permission gate
    permission_gate_enabled: bool = True
    permission_gate_medium_timeout_seconds: int = 300
    permission_gate_high_timeout_seconds: int = 3600
    # action gate — risk→mode policy (C2). none/low always direct, critical always
    # reject; only medium/high are configurable, and only to non-reject modes.
    action_gate_medium_mode: Literal["direct", "sandbox", "approval"] = "approval"
    action_gate_high_mode: Literal["direct", "sandbox", "approval"] = "approval"
    # provider circuit breaker
    provider_failure_threshold: int = 3
    provider_cooldown_seconds: int = 60
    # ── per-agent deployment / process knobs (defaults mirror Settings) ──
    log_format: str = "console"
    session_ttl_days: int = 30
    session_max_total_mb: int = 1024
    session_max_count: int = 10000
    session_cleanup_interval_seconds: float = 3600.0
    disabled_skills: list[str] = Field(default_factory=list)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    diagnostics: DiagnosticsSettings = Field(default_factory=DiagnosticsSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)
    scheduling: SchedulingSettings = Field(default_factory=SchedulingSettings)
    webhooks: WebhooksSettings = Field(default_factory=WebhooksSettings)
    im: ImBinding = Field(default_factory=ImBinding)
    bindings: AgentBindings = Field(default_factory=AgentBindings)
    approval: ApprovalRouting | None = None


def resolve_approvers(
    routing: ApprovalRouting,
    risk_level: str,
    tool_name: str,
) -> tuple[list[tuple[str, str]], str]:
    """Resolve approver addresses and quorum policy for a tool call.

    Returns ``([(platform, target_id), ...], policy)``.  Empty list means no
    approvers were found — the caller must apply ``on_no_approver`` (default-closed).

    Resolution order: ``by_tool`` overrides ``by_risk``.  Each approver string
    must be in ``platform:target_id`` format, except the literal ``requester``
    sentinel which resolves to ``("requester", "")`` — route the prompt back to
    the requesting conversation. ``requester:<target>`` is reserved (never an
    outbound platform); malformed entries are silently skipped.
    """
    entry = routing.by_tool.get(tool_name)
    if entry is None:
        if risk_level == "medium":
            entry = routing.by_risk.medium
        elif risk_level == "high":
            entry = routing.by_risk.high

    if entry is None:
        return [], "any"

    addresses: list[tuple[str, str]] = []
    for raw in entry.approvers:
        if raw == REQUESTER_SENTINEL:
            addresses.append((REQUESTER_SENTINEL, ""))
            continue
        if ":" not in raw:
            continue
        platform, _, target = raw.partition(":")
        if platform == REQUESTER_SENTINEL:
            continue
        if platform and target:
            addresses.append((platform, target))

    return addresses, entry.policy


@dataclass(frozen=True)
class AgentConfigIndex:
    """In-memory resolution index built from scanning the agents directory."""

    agents: dict[str, AgentFile]
    default: str | None

    def get(self, name: str) -> AgentFile | None:
        return self.agents.get(name)

    def default_agent(self) -> str | None:
        return self.default

    def slack_agents(self) -> list[str]:
        """Names of agents that declare a Slack IM binding."""
        return [name for name, a in self.agents.items() if a.im.slack is not None]

    def telegram_agents(self) -> list[str]:
        """Names of agents that declare a Telegram IM binding."""
        return [name for name, a in self.agents.items() if a.im.telegram is not None]


# Current published index. Empty until scan() runs (mirrors skill_registry._index).
_index = AgentConfigIndex(agents={}, default=None)


def _resolve_agents_dir(agents_dir: str | Path | None) -> Path:
    """Return the agents root, falling back to env then the default."""
    if agents_dir is not None:
        return Path(agents_dir)
    # Evaluate paths.agents_dir() at call time so FLEETENT_HOME monkeypatching in
    # tests takes effect. AGENTS_DIR module constant stays for backwards compat.
    return Path(os.environ.get("FLEETENT_AGENTS_DIR", str(paths.agents_dir())))


def load_agent_file(agent_dir: Path) -> AgentFile:
    """Parse ``<agent_dir>/agent.yaml`` and validate the directory name matches ``name``."""
    path = agent_dir / AGENT_FILE_NAME
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping")
    raw = _drop_ignored_legacy_governance_keys(raw)
    agent = AgentFile.model_validate(raw)
    if agent.name != agent_dir.name:
        raise ValueError(
            f"agent directory '{agent_dir.name}' does not match in-file name "
            f"'{agent.name}' ({path})"
        )
    _reject_inline_secrets(agent, path)
    return agent


def _reject_inline_secrets(agent: AgentFile, path: Path) -> None:
    """Reject inline plaintext secrets in MCP/IM binding defs; secrets go via env refs."""
    payload = {
        "mcp_servers": [server.model_dump() for server in agent.mcp_servers],
        "im": agent.im.model_dump(),
    }
    intelligence_payload = {
        "models": agent.models.model_dump(),
        "embedding": agent.embedding.model_dump(),
        "rerank": agent.rerank.model_dump(),
        "knowledge": agent.knowledge.model_dump(),
    }
    for key, value in flatten(payload):
        # Skip structural, non-secret fields: CLI args (e.g. npm package specs), command
        # names, plain ids, transport names. `.url` is intentionally NOT skipped — a URL
        # may embed a credential (e.g. ?token=...) and must still be scanned.
        if any(seg in key for seg in (".args.", ".command", ".id", ".transport")):
            continue
        if (
            isinstance(value, str)
            and looks_inline_secret(value)
            and not _is_env_reference(key, value)
        ):
            raise ValueError(
                f"inline secret-like value in agent '{agent.name}' at '{key}' ({path}); "
                "reference secrets by environment-variable name instead"
            )
    for key, value in flatten(intelligence_payload):
        if not _is_secret_reference_key(key) or not isinstance(value, str):
            continue
        if looks_inline_secret(value) and not _is_env_reference(key, value):
            raise ValueError(
                f"inline secret-like value in agent '{agent.name}' at '{key}' ({path}); "
                "reference secrets by environment-variable name instead"
            )


def _is_env_reference(key: str, value: str) -> bool:
    if key.endswith("_env"):
        return _ENV_VAR_NAME_RE.fullmatch(value) is not None
    if key.endswith("credential_ref"):
        return _ENV_VAR_NAME_RE.fullmatch(value) is not None or value.startswith("file://")
    # Allow env:VAR_NAME syntax in any field (e.g. mcp_servers[*].env dict values) so
    # secrets can live in .env and be referenced without being flagged as inline secrets.
    if value.startswith("env:"):
        return _ENV_VAR_NAME_RE.fullmatch(value) is not None
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
    raw = _drop_ignored_legacy_governance_keys(raw)
    agent = AgentFile.model_validate(raw)
    _reject_inline_secrets(agent, path)
    return agent


def _single_agent_index(agent: AgentFile) -> AgentConfigIndex:
    """Build an index from one single-file agent: it is the sole, forced-default agent."""
    return AgentConfigIndex(agents={agent.name: agent}, default=agent.name)


def _drop_ignored_legacy_governance_keys(raw: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in raw.items() if key not in _IGNORED_LEGACY_GOVERNANCE_KEYS}


def build_index(agents_dir: str | Path | None = None) -> AgentConfigIndex:
    """Build a fresh resolution index (pure; no globals).

    Default installed Agent mode: when no explicit ``agents_dir`` /
    ``FLEETENT_AGENTS_DIR`` is given and ``agents/default/agent.yaml`` exists, load it
    as the sole, forced-default agent. The old home-root ``agent.yaml`` single-file
    mode is not a current MVP deployment path. Otherwise scan the agents directory.
    """
    if agents_dir is None and "FLEETENT_AGENTS_DIR" not in os.environ:
        default_file = paths.agent_file()
        if default_file.is_file():
            return _single_agent_index(load_agent_file(default_file.parent))

    root = _resolve_agents_dir(agents_dir)
    agents: dict[str, AgentFile] = {}
    default: str | None = None

    if root.is_dir():
        for agent_dir in sorted(p for p in root.iterdir() if (p / AGENT_FILE_NAME).is_file()):
            agent = load_agent_file(agent_dir)
            agents[agent.name] = agent
            if agent.bindings.default and default is None:
                default = agent.name

    return AgentConfigIndex(agents=agents, default=default)


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
