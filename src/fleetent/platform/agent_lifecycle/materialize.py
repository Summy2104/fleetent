"""Materialize a runnable agent home from an authored definition (DB→file export).

The platform authors agents; this writes each agent's self-contained home —
``FLEETENT_HOME/<name>/agent.yaml`` (the full home schema) plus a ``.env`` scaffold that
references secrets by env-var name only (never plaintext) — so the agent is runnable by
``fleetent agent run`` (see openspec change ``platform-agent-lifecycle``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from fleetent import agent_store, paths
from fleetent.agent_config import (
    AGENT_FILE_NAME,
    AgentBindings,
    AgentFile,
    AgentKnowledge,
    AgentKnowledgeBinding,
    AgentModels,
    ModelRouteEntry,
    ModelTarget,
    default_models,
)
from fleetent.config import McpServerSettings
from fleetent.intelligence.knowledge_base.config import KnowledgeConfigSnapshot
from fleetent.platform.config_validation import _flatten
from fleetent.platform.connector_management import agent_mcp_server_store
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.model_provider_management import provider_admin_store


def _models_from_overrides(model_overrides: dict[str, Any]) -> AgentModels:
    """Expand per-route provider selections into real targets/routes.

    Each route key maps to a chosen provider id; the provider config supplies base_url,
    model, protocol and ``api_key_env`` (reused at the provider level, not re-authored
    per agent). Routes referencing the same provider share one target. Falls back to the
    neutral local default policy when no providers are selected.
    """
    targets: dict[str, ModelTarget] = {}
    routes: dict[str, list[ModelRouteEntry]] = {}
    for route_key, sel in model_overrides.items():
        # Only the console's {route: {provider, model}} shape expands to a target; other
        # legacy shapes (e.g. {"model": "fast"}) are ignored and fall back to defaults.
        if not isinstance(sel, dict):
            continue
        provider_id = sel.get("provider")
        if not provider_id:
            continue
        provider = provider_admin_store.get_provider(provider_id)
        if provider is None:
            continue
        if provider_id not in targets:
            targets[provider_id] = ModelTarget(
                id=provider_id,
                provider=str(provider.get("provider") or provider_id),
                protocol=str(provider.get("protocol") or "openai_chat"),
                base_url=provider.get("base_url"),
                model=provider.get("model"),
                api_key_env=provider.get("api_key_env"),
                max_tokens=provider.get("max_tokens"),
                params=provider.get("params") or {},
            )
        routes[route_key] = [ModelRouteEntry(target=provider_id)]
    if not targets:
        return default_models()
    return AgentModels(targets=list(targets.values()), routes=routes)


def _mcp_servers_from_store(agent_id: int) -> list[McpServerSettings]:
    """Assemble bound MCP server definitions (agent-scoped first, then global)."""
    servers: list[McpServerSettings] = []
    for sid in agent_store.list_mcp_servers_for_agent(agent_id):
        row = agent_mcp_server_store.get_mcp_server(
            agent_id, sid
        ) or agent_mcp_server_store.get_mcp_server(None, sid)
        if row is None:
            continue
        servers.append(
            McpServerSettings(
                id=sid,
                transport=str(row.get("transport") or "http"),
                url=str(row.get("url") or ""),
                auth_type=str(row.get("auth_type") or "none"),
                api_key_env=str(row.get("api_key_env") or ""),
                command=str(row.get("command") or ""),
                args=list(row.get("args") or []),
                env=dict(row.get("env") or {}),
            )
        )
    return servers


def _bindings_from_store(agent_id: int) -> AgentBindings:
    channels = [
        f"{c['platform']}:{c['channel_id']}" for c in agent_store.list_channels_for_agent(agent_id)
    ]
    return AgentBindings(channels=channels, users=agent_store.list_users_for_agent(agent_id))


def _knowledge_from_store(tenant_id: str, agent_id: int) -> AgentKnowledge:
    kb_ids = agent_kbs_store.list_kbs_for_agent(tenant_id, str(agent_id))
    if not kb_ids:
        return AgentKnowledge()
    return AgentKnowledge(
        enabled=True,
        bindings=[AgentKnowledgeBinding(tenant_id=tenant_id, kb_id=kb_id) for kb_id in kb_ids],
    )


def agent_file_from_store(agent: agent_store.Agent) -> AgentFile:
    """Build the full home schema from the authored definition + bindings.

    Materializes every field the platform authors: identity (tenant/team), model policy
    (expanded from provider selections), MCP servers, IM bindings and knowledge bindings.
    connectors/access are not yet stored per-agent; they materialize as their safe defaults
    (no connectors; default-closed access) until authoring lands.
    """
    return AgentFile(
        name=agent.name,
        version=1,
        tenant_id=agent.tenant_id,
        team_id=agent.team_id,
        system_prompt=agent.system_prompt,
        allowed_tools=agent.allowed_tools,
        allowed_skills=agent.allowed_skills,
        plugins=agent.plugins,
        features=agent.features,
        skills_dir=agent.skills_dir,
        models=_models_from_overrides(agent.model_overrides),
        memory_namespace=agent.memory_namespace,
        mcp_servers=_mcp_servers_from_store(agent.id),
        bindings=_bindings_from_store(agent.id),
        knowledge=_knowledge_from_store(agent.tenant_id, agent.id),
    )


def home_dir(name: str) -> Path:
    """The agent's home directory: ``FLEETENT_HOME/<name>/`` (matches the runtime)."""
    return paths.base_dir() / name


def _env_var_names(
    agent: AgentFile,
    knowledge_config: KnowledgeConfigSnapshot | None = None,
) -> list[str]:
    """Collect the env-var names the agent's home references (connectors + MCP)."""
    names: list[str] = []
    slack = agent.connectors.slack
    if slack is not None:
        names.extend([slack.bot_token_env, slack.app_token_env])
    for server in agent.mcp_servers:
        if server.api_key_env:
            names.append(server.api_key_env)
    for target in agent.models.targets:
        if target.api_key_env:
            names.append(target.api_key_env)
    if knowledge_config is not None:
        for key, value in _flatten(knowledge_config.model_dump(mode="json")):
            if key.endswith("_env") and isinstance(value, str) and value:
                names.append(value)
    # stable order, de-duplicated
    seen: set[str] = set()
    ordered: list[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, val = stripped.split("=", 1)
        values[key.strip()] = val
    return values


def _seed_env(home: Path, names: list[str]) -> None:
    """Write/refresh ``.env`` with the referenced names, preserving operator values.

    Existing values are kept verbatim; missing names are added with an empty value. No
    secret value is ever written by the platform.
    """
    env_path = home / ".env"
    existing = _parse_env(env_path.read_text(encoding="utf-8")) if env_path.exists() else {}
    lines = [f"{name}={existing.get(name, '')}" for name in names]
    # keep any operator-added vars not referenced by the definition
    for key, val in existing.items():
        if key not in names:
            lines.append(f"{key}={val}")
    env_path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")


def materialize_from_store(name: str) -> Path | None:
    """Materialize the home for a stored agent by name (the DB→file export on write).

    Returns the home dir, or None if no such agent exists. Best-effort callers may ignore
    a None (e.g. a delete racing a materialize).
    """
    agent = agent_store.get_by_name(name)
    if agent is None:
        return None
    return write_home(agent_file_from_store(agent))


def write_home(
    agent: AgentFile,
    *,
    knowledge_config: KnowledgeConfigSnapshot | None = None,
) -> Path:
    """Materialize ``agent``'s home and return its directory.

    Rewrites ``agent.yaml`` from the definition and seeds/refreshes the ``.env`` scaffold.
    Idempotent: re-running rewrites the yaml and preserves operator ``.env`` values.
    """
    home = home_dir(agent.name)
    home.mkdir(parents=True, exist_ok=True)
    payload = agent.model_dump(mode="json", exclude_defaults=False)
    (home / AGENT_FILE_NAME).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    if knowledge_config is not None:
        write_knowledge_config(knowledge_config)
    _seed_env(home, _env_var_names(agent, knowledge_config))
    return home


def write_knowledge_config(
    knowledge_config: KnowledgeConfigSnapshot,
    *,
    service_home: Path | None = None,
) -> Path:
    """Materialize KB construction config to platform or standalone service home."""
    config_dir = (service_home / "config") if service_home is not None else paths.config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "knowledge.yaml"
    path.write_text(
        yaml.safe_dump(_knowledge_payload(knowledge_config), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def _knowledge_payload(knowledge_config: KnowledgeConfigSnapshot) -> dict[str, object]:
    payload = knowledge_config.model_dump(mode="json", exclude_defaults=False)
    for kb in payload["knowledge_bases"]:
        for source in kb["sources"]:
            source.pop("tenant_id", None)
            source.pop("kb_id", None)
    return payload
