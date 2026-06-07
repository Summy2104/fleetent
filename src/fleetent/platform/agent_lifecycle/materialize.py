"""Materialize a runnable agent home from an authored definition (DB→file export).

The platform authors agents; this writes each agent's self-contained home —
``FLEETENT_HOME/<name>/agent.yaml`` (the full home schema) plus a ``.env`` scaffold that
references secrets by env-var name only (never plaintext) — so the agent is runnable by
``fleetent agent run`` (see openspec change ``platform-agent-lifecycle``).
"""

from __future__ import annotations

from collections.abc import Callable
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
from fleetent.platform.im_gateway_management import list_im_identities
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.model_provider_management import provider_admin_store
from fleetent.platform.secret_management import agent_secret_store

# Resolves an env-var name to its inject-mode value, or None for operator-mode slots.
SecretResolver = Callable[[str], str | None]


def _target_from_provider(provider_id: str) -> ModelTarget | None:
    """Build a ModelTarget from a configured provider (api_key_env reused at the provider
    level). Returns None if the provider no longer exists."""
    provider = provider_admin_store.get_provider(provider_id)
    if provider is None:
        return None
    return ModelTarget(
        id=provider_id,
        provider=str(provider.get("provider") or provider_id),
        protocol=str(provider.get("protocol") or "openai_chat"),
        base_url=provider.get("base_url"),
        model=provider.get("model"),
        api_key_env=provider.get("api_key_env"),
        max_tokens=provider.get("max_tokens"),
        params=provider.get("params") or {},
    )


def _route_entries(value: Any, targets: dict[str, ModelTarget]) -> list[ModelRouteEntry]:
    """Build a route's ordered fallback entries, dropping any whose target isn't selected.

    Accepts a single provider id (``"pid"``), a list of ids, or a list of full entries
    ``{target, max_tokens, params}`` — the structure the console router authors.
    """
    raw = value if isinstance(value, list) else [value]
    entries: list[ModelRouteEntry] = []
    for item in raw:
        tid: Any
        max_tokens: Any
        params: dict[str, Any]
        if isinstance(item, str):
            tid, max_tokens, params = item, None, {}
        elif isinstance(item, dict):
            tid = item.get("target")
            max_tokens = item.get("max_tokens")
            params = item.get("params") or {}
        else:
            continue
        if tid in targets:
            entries.append(ModelRouteEntry(target=str(tid), max_tokens=max_tokens, params=params))
    return entries


def _models_from_targets_routes(target_ids: list[Any], routes_sel: dict[str, Any]) -> AgentModels:
    """New console shape: a selected model list + a route→ordered-fallback-entries map."""
    targets: dict[str, ModelTarget] = {}
    for pid in target_ids:
        if isinstance(pid, str) and pid not in targets:
            target = _target_from_provider(pid)
            if target is not None:
                targets[pid] = target
    if not targets:
        return default_models()
    routes: dict[str, list[ModelRouteEntry]] = {}
    for route_key, value in routes_sel.items():
        entries = _route_entries(value, targets)
        if entries:
            routes[route_key] = entries
    if not routes:  # at least a default route so the policy is runnable
        routes["default"] = [ModelRouteEntry(target=next(iter(targets)))]
    return AgentModels(targets=list(targets.values()), routes=routes)


def _models_from_overrides(model_overrides: dict[str, Any]) -> AgentModels:
    """Expand the agent's model selection into real targets/routes.

    New shape ``{targets: [provider_id], routes: {route: provider_id}}`` — a checked model
    list plus a routing map. Legacy shape ``{route: {provider, model}}`` is still accepted.
    The provider config supplies base_url/model/protocol/``api_key_env`` (reused at the
    provider level). Falls back to the neutral local default policy when nothing is selected.
    """
    target_ids = model_overrides.get("targets")
    if isinstance(target_ids, list):
        return _models_from_targets_routes(target_ids, model_overrides.get("routes") or {})

    # Legacy {route: {provider, model}} — one provider per route.
    targets: dict[str, ModelTarget] = {}
    routes: dict[str, list[ModelRouteEntry]] = {}
    for route_key, sel in model_overrides.items():
        if not isinstance(sel, dict):
            continue
        provider_id = sel.get("provider")
        if not provider_id or provider_id in targets:
            if provider_id and provider_id in targets:
                routes[route_key] = [ModelRouteEntry(target=provider_id)]
            continue
        target = _target_from_provider(provider_id)
        if target is None:
            continue
        targets[provider_id] = target
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
    # users bind by raw IM user id (e.g. the Slack/Telegram/WhatsApp user id, no platform
    # prefix): expand each internal user to its platform_user_id handles so the deployed
    # agent matches incoming IM messages directly without a platform-DB lookup.
    users = [
        str(ident["platform_user_id"])
        for uid in agent_store.list_users_for_agent(agent_id)
        for ident in list_im_identities(uid)
    ]
    return AgentBindings(channels=channels, users=users)


def _knowledge_from_store(tenant_id: str, agent_id: int) -> AgentKnowledge:
    kb_ids = agent_kbs_store.list_kbs_for_agent(tenant_id, str(agent_id))
    if not kb_ids:
        return AgentKnowledge()
    return AgentKnowledge(
        enabled=True,
        bindings=[AgentKnowledgeBinding(tenant_id=tenant_id, kb_id=kb_id) for kb_id in kb_ids],
    )


def _active_version(agent: agent_store.Agent) -> int:
    """The agent's active version number (the real snapshot count), defaulting to 1."""
    if agent.active_version_id is not None:
        av = agent_store.get_version_by_id(agent.active_version_id)
        if av is not None:
            return av.version
    return 1


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``over`` onto ``base`` (dicts merge, scalars/lists replace)."""
    out = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _apply_overrides(base: AgentFile, overrides: dict[str, Any]) -> AgentFile:
    """Deep-merge per-agent agent.yaml overrides onto the base, re-validating the result.

    Lets operators configure any agent.yaml field (governance/deployment/intelligence/
    access/…) without a column per knob. A malformed override is ignored (base kept) so a
    bad value can never break deploy/preview.
    """
    if not overrides:
        return base
    try:
        merged = _deep_merge(base.model_dump(mode="json", exclude_defaults=False), overrides)
        return AgentFile.model_validate(merged)
    except Exception:  # noqa: BLE001 — invalid override must not break materialize
        return base


def agent_file_from_store(agent: agent_store.Agent) -> AgentFile:
    """Build the full home schema from the authored definition + bindings.

    Materializes identity (tenant/team), model policy (expanded from provider selections),
    MCP servers, IM bindings and knowledge bindings, then deep-merges config_overrides so
    any agent.yaml field is configurable.
    """
    base = AgentFile(
        name=agent.name,
        version=_active_version(agent),
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
    return _apply_overrides(base, agent.config_overrides)


def home_dir(name: str) -> Path:
    """The agent's home directory: ``FLEETENT_HOME/<name>/`` (matches the runtime)."""
    return paths.base_dir() / name


def required_env_slots(
    agent: AgentFile,
    knowledge_config: KnowledgeConfigSnapshot | None = None,
) -> list[tuple[str, str]]:
    """Every ``*_env`` the agent's home references, as ``(env_name, source_label)``.

    Source labels group the slot by purpose (Connectors / MCP / Models / Knowledge) for
    the console's required-secrets panel. Stable order, de-duplicated by env name (first
    label wins).
    """
    slots: list[tuple[str, str]] = []
    slack = agent.connectors.slack
    if slack is not None:
        slots.append((slack.bot_token_env, "Connectors·slack"))
        slots.append((slack.app_token_env, "Connectors·slack"))
    for server in agent.mcp_servers:
        if server.api_key_env:
            slots.append((server.api_key_env, f"MCP·{server.id}"))
    for target in agent.models.targets:
        if target.api_key_env:
            slots.append((target.api_key_env, f"Models·{target.id}"))
    if knowledge_config is not None:
        for key, value in _flatten(knowledge_config.model_dump(mode="json")):
            if key.endswith("_env") and isinstance(value, str) and value:
                slots.append((value, "Knowledge"))
    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    for name, label in slots:
        if name and name not in seen:
            seen.add(name)
            ordered.append((name, label))
    return ordered


def _env_var_names(
    agent: AgentFile,
    knowledge_config: KnowledgeConfigSnapshot | None = None,
) -> list[str]:
    """Collect the env-var names the agent's home references (connectors + MCP)."""
    return [name for name, _ in required_env_slots(agent, knowledge_config)]


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
    secret_resolver: SecretResolver | None = None,
) -> None:
    """Write/refresh ``.env`` with the referenced names, resolving by credential mode.

    A ``secret_resolver`` (bound to an agent) supplies inject-mode values: when it returns
    a value for a name, that value is written (``NAME=value``); when it returns None the
    slot is operator-mode and the existing operator value is preserved (or left blank). No
    operator value is ever overwritten by the platform.
    """
    env_path = home / ".env"
    existing = _parse_env(env_path.read_text(encoding="utf-8")) if env_path.exists() else {}
    lines: list[str] = []
    for name in names:
        injected = secret_resolver(name) if secret_resolver is not None else None
        lines.append(f"{name}={injected if injected is not None else existing.get(name, '')}")
    # keep any operator-added vars not referenced by the definition
    for key, val in existing.items():
        if key not in names:
            lines.append(f"{key}={val}")
    env_path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")


def materialize_from_store(name: str) -> Path | None:
    """Materialize the home for a stored agent by name (the DB→file export on write).

    inject-mode credential values are decrypted into ``.env``; operator slots stay blank.
    Returns the home dir, or None if no such agent exists. Best-effort callers may ignore
    a None (e.g. a delete racing a materialize).
    """
    agent = agent_store.get_by_name(name)
    if agent is None:
        return None

    def resolver(env_name: str) -> str | None:
        return agent_secret_store.get_decrypted(agent.id, env_name)

    return write_home(agent_file_from_store(agent), secret_resolver=resolver)


def write_home(
    agent: AgentFile,
    *,
    knowledge_config: KnowledgeConfigSnapshot | None = None,
    secret_resolver: SecretResolver | None = None,
) -> Path:
    """Materialize ``agent``'s home and return its directory.

    Rewrites ``agent.yaml`` (pure ``*_env`` references, never a secret value) and seeds the
    ``.env`` scaffold, resolving inject-mode values via ``secret_resolver``. Idempotent:
    re-running rewrites the yaml and preserves operator ``.env`` values.
    """
    home = home_dir(agent.name)
    home.mkdir(parents=True, exist_ok=True)
    payload = agent.model_dump(mode="json", exclude_defaults=False)
    (home / AGENT_FILE_NAME).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    if knowledge_config is not None:
        write_knowledge_config(knowledge_config)
    _seed_env(home, _env_var_names(agent, knowledge_config), secret_resolver)
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
