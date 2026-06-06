"""Materialize a runnable agent home from an authored definition (DB→file export).

The platform authors agents; this writes each agent's self-contained home —
``FLEETENT_HOME/agents/<name>/agent.yaml`` (the full home schema) plus a ``.env`` scaffold that
references secrets by env-var name only (never plaintext) — so the agent is runnable by
``fleetent agent run`` (see openspec change ``platform-agent-lifecycle``).
"""

from __future__ import annotations

import sqlite3
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
from fleetent.observability.structured_logging import get_logger
from fleetent.platform.agent_lifecycle import credential_slots, secret_store
from fleetent.platform.config_validation import _flatten
from fleetent.platform.connector_management import agent_mcp_server_store
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.model_provider_management import provider_admin_store

_logger = get_logger("agent_lifecycle.materialize")


def agent_file_from_store(agent: agent_store.Agent) -> AgentFile:
    """Build the home schema from the authored core definition.

    connectors/access are not yet stored per-agent on the platform; they materialize as
    their safe defaults (no connectors; default-closed access) until authoring lands.
    """
    return AgentFile(
        name=agent.name,
        version=1,
        tenant_id=agent.tenant_id,
        team_id=agent.team_id,
        system_prompt=agent.system_prompt,
        allowed_tools=agent.allowed_tools,
        skills_dir=agent.skills_dir,
        allowed_skills=agent.allowed_skills,
        plugins=agent.plugins,
        features=agent.features,
        models=_models_from_overrides(agent.model_overrides),
        mcp_servers=_mcp_servers_for_agent(agent),
        bindings=_bindings_for_agent(agent),
        knowledge=_knowledge_for_agent(agent),
        memory_namespace=agent.memory_namespace,
    )


def _models_from_overrides(model_overrides: dict[str, Any]) -> AgentModels:
    """Expand DB-authored provider selections into the runtime model policy."""
    route_overrides = {
        k: v for k, v in model_overrides.items() if k != credential_slots.RESERVED_KEY
    }
    if not route_overrides:
        return default_models()

    targets: dict[str, ModelTarget] = {}
    routes: dict[str, list[ModelRouteEntry]] = {}
    for route_key, raw_entries in route_overrides.items():
        entries = raw_entries if isinstance(raw_entries, list) else [raw_entries]
        route_entries: list[ModelRouteEntry] = []
        for index, raw_entry in enumerate(entries):
            if not isinstance(raw_entry, dict):
                continue
            target = _target_from_model_override(route_key, index, raw_entry)
            targets.setdefault(target.id, target)
            route_entries.append(
                ModelRouteEntry(
                    target=target.id,
                    max_tokens=raw_entry.get("max_tokens"),
                    params=raw_entry.get("params") or {},
                )
            )
        if route_entries:
            routes[str(route_key)] = route_entries

    if not targets or not routes:
        return default_models()
    return AgentModels(targets=list(targets.values()), routes=routes)


def _target_from_model_override(route_key: str, index: int, entry: dict[str, Any]) -> ModelTarget:
    provider_id = entry.get("provider_id")
    provider = provider_admin_store.get_provider(str(provider_id)) if provider_id else None
    source = {**(provider or {}), **{k: v for k, v in entry.items() if k != "provider_id"}}
    params = (provider or {}).get("params") or (provider or {}).get("extra_params") or {}
    if not provider:
        params = (
            entry.get("target_params") or entry.get("params") or entry.get("extra_params") or {}
        )
    target_id = str(provider_id or entry.get("id") or f"{route_key}-{index}")
    protocol = str(source.get("protocol") or "openai_chat")
    base_url = source.get("base_url")
    endpoint = source.get("endpoint")
    if protocol in {"http_embedding", "http_rerank", "openai_image_generation"}:
        endpoint = endpoint or base_url
        base_url = None
    return ModelTarget(
        id=target_id,
        provider=str(source.get("provider") or provider_id or "custom"),
        protocol=protocol,
        base_url=base_url,
        endpoint=endpoint,
        model=source.get("model"),
        api_key_env=source.get("api_key_env"),
        max_tokens=source.get("max_tokens"),
        params=params,
    )


def _mcp_servers_for_agent(agent: agent_store.Agent) -> list[McpServerSettings]:
    ids = list(
        dict.fromkeys(
            [*(agent.mcp_server_ids or []), *agent_store.list_mcp_servers_for_agent(agent.id)]
        )
    )
    servers: list[McpServerSettings] = []
    for server_id in ids:
        row = agent_mcp_server_store.get_mcp_server(
            agent.id, server_id
        ) or agent_mcp_server_store.get_mcp_server(None, server_id)
        if row is None:
            continue
        servers.append(
            McpServerSettings(
                id=server_id,
                transport=row["transport"],
                url=row["url"],
                auth_type=row["auth_type"],
                api_key_env=row["api_key_env"],
                command=row["command"],
                args=row["args"] or [],
                env=row["env"] or {},
            )
        )
    return servers


def _bindings_for_agent(agent: agent_store.Agent) -> AgentBindings:
    return AgentBindings(
        channels=[
            f"{channel['platform']}:{channel['channel_id']}"
            for channel in agent_store.list_channels_for_agent(agent.id)
        ],
        users=agent_store.list_users_for_agent(agent.id),
    )


def _knowledge_for_agent(agent: agent_store.Agent) -> AgentKnowledge:
    try:
        kb_ids = agent_kbs_store.list_kbs_for_agent(agent.tenant_id, str(agent.id))
    except sqlite3.OperationalError as exc:
        if "no such table: agent_kbs" not in str(exc):
            raise
        kb_ids = []
    if not kb_ids:
        return AgentKnowledge()
    return AgentKnowledge(
        enabled=True,
        bindings=[
            AgentKnowledgeBinding(
                tenant_id=agent.tenant_id,
                kb_id=kb_id,
                default=index == 0,
            )
            for index, kb_id in enumerate(kb_ids)
        ],
    )


def home_dir(name: str) -> Path:
    """The agent's home directory: ``FLEETENT_HOME/agents/<name>/``."""
    return paths.base_dir() / "agents" / name


def _env_var_names(
    agent: AgentFile,
) -> list[str]:
    """Collect the env-var names the agent's home references."""
    names: list[str] = []
    for key, value in _flatten(agent.model_dump(mode="json")):
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


def _knowledge_env_var_names(knowledge_config: KnowledgeConfigSnapshot | None) -> set[str]:
    """Collect Platform-owned Knowledge construction env names to exclude from Agent env."""
    if knowledge_config is None:
        return set()
    names: set[str] = set()
    for key, value in _flatten(knowledge_config.model_dump(mode="json")):
        if key.endswith("_env") and isinstance(value, str) and value:
            names.add(value)
    return names


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, val = stripped.split("=", 1)
        values[key.strip()] = val
    return values


def _seed_env(
    home: Path,
    names: list[str],
    *,
    source_agent: agent_store.Agent | None = None,
    exclude_existing: set[str] | None = None,
) -> None:
    """Write/refresh ``.env`` with the referenced names, preserving operator values.

    Existing values are kept verbatim; missing names are added with an empty value. No
    secret value is ever written by the platform.
    """
    env_path = home / ".env"
    existing = _parse_env(env_path.read_text(encoding="utf-8")) if env_path.exists() else {}
    slots_by_env = (
        {slot.env_name: slot for slot in credential_slots.list_slots(source_agent)}
        if source_agent is not None
        else {}
    )
    lines: list[str] = []
    for name in names:
        slot = slots_by_env.get(name)
        if source_agent is not None and slot is not None and slot.mode == "inject":
            value = (
                secret_store.get_decrypted(source_agent.id, name)
                if secret_store.status(source_agent.id, name) == "set"
                else ""
            )
        else:
            value = existing.get(name, "")
        lines.append(f"{name}={value}")
    # keep any operator-added vars not referenced by the definition
    excluded = exclude_existing or set()
    for key, val in existing.items():
        if key in excluded:
            continue
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
    return write_home(agent_file_from_store(agent), source_agent=agent)


def write_home(
    agent: AgentFile,
    *,
    knowledge_config: KnowledgeConfigSnapshot | None = None,
    source_agent: agent_store.Agent | None = None,
) -> Path:
    """Materialize ``agent``'s home and return its directory.

    Rewrites ``agent.yaml`` from the definition and seeds/refreshes the ``.env`` scaffold.
    Idempotent: re-running rewrites the yaml and preserves operator ``.env`` values.
    """
    home = home_dir(agent.name)
    home.mkdir(parents=True, exist_ok=True)
    _logger.debug("agent_home_write_start", name=agent.name, path=str(home))
    (home / "data").mkdir(parents=True, exist_ok=True)
    payload = agent.model_dump(mode="json", exclude_defaults=False)
    (home / AGENT_FILE_NAME).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    _seed_env(
        home,
        _env_var_names(agent),
        source_agent=source_agent,
        exclude_existing=_knowledge_env_var_names(knowledge_config),
    )
    return home
