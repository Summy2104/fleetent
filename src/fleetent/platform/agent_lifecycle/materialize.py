"""Materialize a runnable agent home from an authored definition (DB→file export).

The platform authors agents; this writes each agent's self-contained home —
``FLEETENT_HOME/agents/<name>/agent.yaml`` (the full home schema) plus a ``.env`` scaffold that
references secrets by env-var name only (never plaintext) — so the agent is runnable by
``fleetent agent run`` (see openspec change ``platform-agent-lifecycle``).
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from fleetent import agent_store, paths
from fleetent.agent_config import (
    AGENT_FILE_NAME,
    AgentFile,
    AgentKnowledge,
    AgentKnowledgeBinding,
    AgentModels,
    ModelRouteEntry,
    ModelTarget,
    default_models,
)
from fleetent.config import McpServerSettings
from fleetent.observability.structured_logging import get_logger
from fleetent.platform.agent_lifecycle import credential_slots, secret_store
from fleetent.platform.connector_management import agent_mcp_server_store
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.model_provider_management import provider_admin_store
from fleetent.platform.skill_management import skill_admin_store
from fleetent.secret_scan import flatten
from fleetent.skills import registry as skill_registry

if TYPE_CHECKING:
    from fleetent.knowledge_base.config import KnowledgeConfigSnapshot

_logger = get_logger("agent_lifecycle.materialize")


def _active_version(agent: agent_store.Agent) -> int:
    """The agent's active version number (the real snapshot count), defaulting to 1.

    Tolerates a legacy/partial DB without the ``agent_versions`` table (returns 1).
    """
    if agent.active_version_id is None:
        return 1
    try:
        av = agent_store.get_version_by_id(agent.active_version_id)
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        return 1
    return av.version if av is not None else 1


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
    """Build the home schema from the authored core definition.

    connectors/access are not yet stored per-agent on the platform; they materialize as
    their safe defaults (no connectors; default-closed access) until authoring lands.
    Finally deep-merges the per-agent ``config_overrides`` so any agent.yaml field is
    configurable without a dedicated column.
    """
    base = AgentFile(
        name=agent.name,
        version=_active_version(agent),
        tenant_id=agent.tenant_id,
        team_id=agent.team_id,
        system_prompt=agent.system_prompt,
        allowed_tools=agent.allowed_tools,
        skills_dir=agent.skills_dir,
        allowed_skills=_allowed_skills_for(agent),
        disabled_skills=_global_disabled_skills(),
        plugins=agent.plugins,
        features=agent.features,
        models=_models_from_overrides(agent.model_overrides),
        mcp_servers=_mcp_servers_for_agent(agent),
        knowledge=_knowledge_for_agent(agent),
        memory_namespace=agent.memory_namespace,
    )
    return _apply_overrides(base, agent.config_overrides)


def _global_disabled_skills() -> list[str]:
    """Skill names globally disabled in the admin store (agent reads only agent.yaml).

    Returns the names with ``global_enabled=0`` so the agent runtime suppresses them
    via ``AgentFile.disabled_skills``. Missing table (legacy DB) safely yields [].
    """
    try:
        states = skill_admin_store.list_states()
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        return []
    return [s["skill_name"] for s in states if not s["global_enabled"]]


def _allowed_skills_for(agent: agent_store.Agent) -> list[str]:
    """Resolve the agent's catalog narrowing from the agent_skills binding matrix.

    With at least one binding row, the result is exactly the ``enabled=1`` subset
    (possibly empty — an explicit narrowing to no skills). Without any binding row,
    fall back to the authored ``allowed_skills``. Missing table (legacy DB) falls
    back to authored too.
    """
    try:
        if skill_admin_store.has_any_binding(str(agent.id)):
            return sorted(skill_admin_store.enabled_skill_names(str(agent.id)))
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
    return agent.allowed_skills


def _models_from_overrides(model_overrides: dict[str, Any]) -> AgentModels:
    """Expand DB-authored provider selections into the runtime model policy."""
    route_overrides = {
        k: v for k, v in model_overrides.items() if k != credential_slots.RESERVED_KEY
    }
    # Backward-compat: the console's two-part picker stored {targets:[...], routes:{name:[...]}}.
    # The route map lives under "routes"; the flat "targets" list is informational only.
    routes_block = route_overrides.get("routes")
    if isinstance(routes_block, dict):
        route_overrides = routes_block
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
    # A provider id may arrive under any of these keys depending on the authoring path:
    # "provider_id" (canonical), "target" (two-part router), "provider" (console picker).
    provider_id = None
    provider = None
    matched_key = None
    for key in ("provider_id", "target", "provider"):
        candidate = entry.get(key)
        if candidate and (row := provider_admin_store.get_provider(str(candidate))) is not None:
            provider_id, provider, matched_key = candidate, row, key
            break
    # the id-carrying keys are lookup hints, not target fields — drop the matched one plus
    # the always-aliases so a provider id can't leak into the target's vendor/id columns.
    drop = {"provider_id", "target"} | ({matched_key} if matched_key else set())
    source = {**(provider or {}), **{k: v for k, v in entry.items() if k not in drop}}
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
    for key, value in flatten(agent.model_dump(mode="json")):
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
    for key, value in flatten(knowledge_config.model_dump(mode="json")):
        if key.endswith("_env") and isinstance(value, str) and value:
            names.add(value)
    return names


def _provider_key_for_env(env_name: str) -> str | None:
    """A provider's inline plaintext key whose api_key_env matches ``env_name``.

    Lets a provider authored with an inline key seed the agent's ``.env`` without a separate
    inject slot — the provider row is the shared source of truth for that model key.
    """
    for provider in provider_admin_store.list_providers():
        if provider.get("api_key_env") == env_name and provider.get("api_key"):
            return str(provider["api_key"])
    return None


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
        elif source_agent is not None:
            # real materialize (secret/provider tables exist): operator host value →
            # provider inline key → shared secret (e.g. KB token). status() needs no key.
            shared = (
                secret_store.get_decrypted(None, name)
                if secret_store.status(None, name) == "set"
                else ""
            )
            value = existing.get(name, "") or (_provider_key_for_env(name) or "") or shared
        else:
            # bare write_home (no store context): keep the operator value, never touch tables
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


def rematerialize_all() -> list[str]:
    """Re-export every authored agent's home (platform-wide DB→file refresh).

    Best-effort: a single agent's failure is logged and skipped so it never blocks the
    rest. Returns the names successfully re-materialized. Used after a global skill state
    change so every agent.yaml reflects the new decision.
    """
    done: list[str] = []
    for name in agent_store.list_all_names():
        try:
            if materialize_from_store(name) is not None:
                done.append(name)
        except Exception as exc:  # noqa: BLE001 — one agent's failure must not block others
            _logger.warn("rematerialize_failed", agent=name, error=str(exc))
    return done


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
    _copy_skills(home)
    return home


def _copy_skills(home: Path) -> None:
    """Mirror the platform's global skills dir into ``<home>/skills/``.

    Makes the agent home self-contained (the agent process reads only its own home).
    Full copy: visibility is later narrowed at runtime by agent.yaml's allowed_skills /
    disabled_skills. Best-effort: a missing source is skipped; a copy error is logged
    but never aborts materialize (agent.yaml is already written).
    """
    src = Path(skill_registry._resolve_skills_dir(None))
    if not src.exists():
        return
    try:
        shutil.copytree(src, home / "skills", dirs_exist_ok=True)
    except OSError as exc:
        _logger.warn("agent_home_skill_copy_failed", path=str(src), error=str(exc))
