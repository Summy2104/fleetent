"""Materialize a runnable standalone/default-tenant agent home from an authored definition.

This legacy helper exports a self-contained home under the default-tenant shim
(``FLEETENT_HOME/tenants/default/agents/<name>/agent.yaml``) plus a ``.env`` scaffold that
references secrets by env-var name only (never plaintext). Managed deployment no longer uses
this path as the real writer; node reconcile owns managed homes.
"""

from __future__ import annotations

import contextlib
import secrets
import shutil
import sqlite3
from hashlib import sha256
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
    collect_env_var_names,
    default_models,
)
from fleetent.config import MCP_FLEETENT_EXT_DEFAULTS, McpApprovalRule, McpServerSettings
from fleetent.platform.agent_lifecycle import credential_slots, default_binding_store, secret_store
from fleetent.platform.connector_management import mcp_server_store
from fleetent.platform.connector_management.mcp_auth import (
    ApiKeyMcpAuthConfig,
    ApiKeyPerUserMcpAuthConfig,
    OAuthAuthorizationCodeMcpAuthConfig,
    OAuthClientCredentialsMcpAuthConfig,
    parse_mcp_auth_config,
)
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.model_provider_management import model_admin_store, provider_admin_store
from fleetent.platform.skill_management import skill_admin_store
from fleetent.secret_scan import flatten
from fleetent.skills import registry as skill_registry
from fleetent.structured_logging import get_logger

if TYPE_CHECKING:
    from fleetent.knowledge_base.config import KnowledgeConfigSnapshot

_logger = get_logger("agent_lifecycle.materialize")
_TUI_TOKEN_ENV = "FLEETENT_TUI_TOKEN"


def _active_version(agent: agent_store.Agent) -> int:
    """The agent's current config version number, defaulting to 1."""
    return int(getattr(agent, "version", 1) or 1)


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
    except Exception as exc:  # noqa: BLE001 — invalid override must not break materialize
        # Fall back to base so deploy/preview never breaks, but surface the drop: an invalid
        # field (e.g. a dangling model route) silently discards the WHOLE override — including
        # unrelated valid bindings like im.slack credentials — so this must be diagnosable
        # rather than silent (AAA-8267).
        _logger.error("agent_override_validation_failed", agent=base.name, exception=exc)
        return base


def agent_file_from_store(agent: agent_store.Agent) -> AgentFile:
    """Build the home schema from the authored core definition.

    IM binding credentials still come from authored ``config_overrides``. Platform-authored
    IM access state (capability flags, allowed users, per-platform group allowlists) is
    then materialized onto the resulting IM binding config without clobbering those creds.
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
    with_overrides = _apply_overrides(base, agent.config_overrides)
    with_im_access = _materialize_im_access(with_overrides, agent)
    return _materialize_default_binding(with_im_access, agent)


def desired_state_payload_from_agent_file(agent_file: AgentFile) -> dict[str, Any]:
    """Serialize the non-secret subset of an AgentFile for node desired-state delivery."""
    dumped = agent_file.model_dump(mode="json", exclude_defaults=False)
    # Capture each MCP server's string ``env`` values (both ``env:`` references and plaintext
    # literals like ATLASSIAN_USER_EMAIL/SITE_NAME) before secret stripping removes every
    # ``env`` block, so non-secret literals survive to the materialized agent.yaml. Real
    # secrets must still be passed as ``env:VAR`` refs + agent_secrets, never inline plaintext.
    mcp_env_refs = _mcp_env_refs_by_id(dumped)
    payload: dict[str, Any] = _strip_secret_plumbing(dumped)
    # Render MCP servers in the standard ``mcpServers`` map form the agent runtime accepts;
    # the legacy ``mcp_servers`` list is rejected by ``load_agent_file``. Done after secret
    # stripping so ``env``/``credential_ref`` are already removed from each server entry.
    _mcp_payload_to_map(payload)
    # Re-attach the preserved ``env`` values onto the rendered ``mcpServers`` map: ``env:``
    # references (node collects their var names via ``referenced_env_names`` and fills them from
    # secrets) plus plaintext non-secret literals (written verbatim to agent.yaml).
    _restore_mcp_env_refs(payload, mcp_env_refs)
    return payload


def _strip_secret_plumbing(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_secret_plumbing(item) for item in value]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key == "env" or key.endswith("credential_ref"):
                continue
            sanitized[key] = _strip_secret_plumbing(item)
        return sanitized
    return value


def _mcp_env_refs_by_id(dumped: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Per-server string ``env`` values from a dumped AgentFile, keyed by server id.

    All string values are kept — both ``env:VAR`` references (non-secret pointers, like
    ``api_key_env``) and plaintext literals (non-secret identifiers like ATLASSIAN_USER_EMAIL/
    SITE_NAME) — so they survive to the materialized agent.yaml. Non-string values are dropped
    here and left to ``_strip_secret_plumbing``. Real secrets must use ``env:VAR`` refs, never
    inline plaintext.
    """
    refs: dict[str, dict[str, str]] = {}
    for server in dumped.get("mcp_servers") or []:
        if not isinstance(server, dict):
            continue
        env = server.get("env")
        if not isinstance(env, dict):
            continue
        kept = {str(k): v for k, v in env.items() if isinstance(v, str)}
        if kept:
            refs[str(server["id"])] = kept
    return refs


def _restore_mcp_env_refs(payload: dict[str, Any], refs: dict[str, dict[str, str]]) -> None:
    """Re-attach preserved ``env:`` references onto the rendered ``mcpServers`` map (in place)."""
    servers = payload.get("mcpServers")
    if not isinstance(servers, dict):
        return
    for server_id, env in refs.items():
        entry = servers.get(server_id)
        if isinstance(entry, dict):
            entry["env"] = env


def _materialize_im_access(base: AgentFile, agent: agent_store.Agent) -> AgentFile:
    """Project platform-authored IM access state into the agent home config."""
    raw = base.model_dump(mode="json", exclude_defaults=False)
    im = raw.setdefault("im", {})
    im["supports_dm"] = agent.supports_dm
    im["supports_groups"] = agent.supports_groups

    allow_users = agent_store.list_users_for_agent(agent.id)
    groups_by_platform: dict[str, list[str]] = {}
    try:
        group_rows = agent_store.list_im_groups_for_agent(agent.id)
    except sqlite3.OperationalError as exc:
        if "no such table: agent_im_groups" not in str(exc):
            raise
        group_rows = []
    for row in group_rows:
        groups_by_platform.setdefault(row["platform"], []).append(row["group_id"])

    for platform, groups in groups_by_platform.items():
        binding = im.get(platform)
        if not isinstance(binding, dict):
            continue
        access = binding.setdefault("access", {})
        access["allow_users"] = allow_users
        access["allow_groups"] = groups

    for platform in ("slack", "telegram"):
        binding = im.get(platform)
        if not isinstance(binding, dict):
            continue
        access = binding.setdefault("access", {})
        access["allow_users"] = allow_users
        access.setdefault("allow_groups", [])

    return AgentFile.model_validate(raw)


def _materialize_default_binding(base: AgentFile, agent: agent_store.Agent) -> AgentFile:
    raw = base.model_dump(mode="json", exclude_defaults=False)
    bindings = raw.setdefault("bindings", {})
    if default_binding_store.is_default(agent.id):
        bindings["default"] = True
    else:
        bindings.pop("default", None)
    return AgentFile.model_validate(raw)


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
        if skill_admin_store.has_any_binding(agent.id):
            return sorted(skill_admin_store.enabled_skill_names(agent.id))
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
    return agent.allowed_skills


def _models_from_overrides(model_overrides: dict[str, Any]) -> AgentModels:
    """Expand DB-authored provider selections into the runtime model policy.

    Two authoring shapes are supported and may coexist:
    - Named tiers: a ``targets`` block ({tier_name: {model_id, params?, max_tokens?}}) defines
      agent-local reusable targets (e.g. primary/fast/backup); a route entry references one via
      ``{"target": tier_name}``. This mirrors ``agent.example.yaml``.
    - Direct model: a route entry ``{"model_id": id}`` builds its own target from the registry
      (used by the specialized routes — embedding/rerank/image/…).
    """
    filtered = {k: v for k, v in model_overrides.items() if k != credential_slots.RESERVED_KEY}
    targets_block = filtered.get("targets") if isinstance(filtered.get("targets"), dict) else None
    routes_block = filtered.get("routes")
    if isinstance(routes_block, dict):
        route_overrides = routes_block
    elif targets_block is not None:
        route_overrides = {}
    else:
        # Legacy: the whole dict is the route map.
        route_overrides = filtered
    if not route_overrides and targets_block is None:
        return default_models()

    # Merge onto the baseline one route at a time: a route absent from the override must keep
    # its default target rather than disappearing just because some other route was overridden.
    baseline = default_models()
    baseline_targets = {target.id: target for target in baseline.targets}
    routes: dict[str, list[ModelRouteEntry]] = dict(baseline.routes)
    override_targets: dict[str, ModelTarget] = {}

    # Build named tier targets first (target id = tier name) so routes can reference them.
    tier_targets: dict[str, ModelTarget] = {}
    for tier_name, tier_def in (targets_block or {}).items():
        if not isinstance(tier_def, dict):
            continue
        target = _tier_target(str(tier_name), tier_def)
        if target is not None:
            tier_targets[str(tier_name)] = target
            override_targets[str(tier_name)] = target

    for route_key, raw_entries in route_overrides.items():
        entries = raw_entries if isinstance(raw_entries, list) else [raw_entries]
        route_entries: list[ModelRouteEntry] = []
        for index, raw_entry in enumerate(entries):
            if not isinstance(raw_entry, dict):
                continue
            ref = raw_entry.get("target")
            # A `target` referencing a defined tier reuses that tier target.
            if isinstance(ref, str) and ref in tier_targets:
                route_entries.append(
                    ModelRouteEntry(
                        target=ref,
                        max_tokens=raw_entry.get("max_tokens"),
                        params=raw_entry.get("params") or {},
                    )
                )
                continue
            # A `target` that is neither a defined tier nor a registered model is dropped rather
            # than materializing a phantom target (e.g. a route pointing at an unfilled tier slot).
            if (
                isinstance(ref, str)
                and not any(raw_entry.get(k) for k in ("model_id", "provider_id", "provider"))
                and model_admin_store.get_model(ref) is None
            ):
                continue
            target = _target_from_model_override(route_key, index, raw_entry)
            override_targets[target.id] = target
            route_entries.append(
                ModelRouteEntry(
                    target=target.id,
                    max_tokens=raw_entry.get("max_tokens"),
                    params=raw_entry.get("params") or {},
                )
            )
        if route_entries:
            routes[str(route_key)] = route_entries

    # Keep only targets some route still references (drops unfilled/unused tiers and baseline
    # targets whose route was overridden), while preserving those untouched baseline routes rely on.
    referenced_ids = {entry.target for entries in routes.values() for entry in entries}
    targets = {
        target_id: target
        for target_id, target in {**baseline_targets, **override_targets}.items()
        if target_id in referenced_ids
    }
    return AgentModels(targets=list(targets.values()), routes=routes)


def _tier_target(tier_name: str, tier_def: dict[str, Any]) -> ModelTarget | None:
    """Build a named tier target (id = tier name) from a registered model, or None if the slot is
    empty / unresolvable so routes referencing it are dropped rather than pointing at a phantom."""
    candidate = tier_def.get("model_id") or tier_def.get("provider_id") or tier_def.get("model")
    if not candidate:
        return None
    model = model_admin_store.get_model(str(candidate))
    if model is None:
        return None
    provider = provider_admin_store.get_provider(str(model["provider_id"]))
    if provider is None:
        return None
    params = _deep_merge(model.get("params") or {}, tier_def.get("params") or {})
    return ModelTarget(
        id=tier_name,
        provider=str(provider.get("vendor") or provider["id"]),
        protocol=str(model.get("protocol") or "openai_chat"),
        base_url=model.get("base_url"),
        endpoint=model.get("endpoint"),
        model=model.get("model_name"),
        api_key_env=provider.get("api_key_env"),
        max_tokens=tier_def.get("max_tokens") or model.get("max_tokens"),
        params=params,
    )


def _target_from_model_override(route_key: str, index: int, entry: dict[str, Any]) -> ModelTarget:
    model_lookup_keys = ("model_id", "provider_id", "target", "provider")
    for key in model_lookup_keys:
        candidate = entry.get(key)
        if not candidate:
            continue
        model = model_admin_store.get_model(str(candidate))
        if model is None:
            continue
        provider = provider_admin_store.get_provider(str(model["provider_id"]))
        if provider is None:
            continue
        params = _deep_merge(model.get("params") or {}, entry.get("params") or {})
        return ModelTarget(
            id=str(model["id"]),
            provider=str(provider.get("vendor") or provider["id"]),
            protocol=str(model.get("protocol") or "openai_chat"),
            base_url=model.get("base_url"),
            endpoint=model.get("endpoint"),
            model=model.get("model_name"),
            api_key_env=provider.get("api_key_env"),
            max_tokens=entry.get("max_tokens") or model.get("max_tokens"),
            params=params,
        )

    _logger.warn(
        "legacy_model_override_fallback",
        route_key=route_key,
        index=index,
        keys=sorted(entry.keys()),
    )
    provider_id = entry.get("provider_id") or entry.get("target") or entry.get("provider")
    params = entry.get("target_params") or entry.get("params") or entry.get("extra_params") or {}
    protocol = str(entry.get("protocol") or "openai_chat")
    base_url = entry.get("base_url")
    endpoint = entry.get("endpoint")
    if protocol in {"http_embedding", "http_rerank", "openai_image_generation"}:
        endpoint = endpoint or base_url
        base_url = None
    return ModelTarget(
        id=str(provider_id or entry.get("id") or f"{route_key}-{index}"),
        provider=str(entry.get("provider") or provider_id or "custom"),
        protocol=protocol,
        base_url=base_url,
        endpoint=endpoint,
        model=entry.get("model"),
        api_key_env=entry.get("api_key_env"),
        max_tokens=entry.get("max_tokens"),
        params=params,
    )


def _mcp_servers_for_agent(agent: agent_store.Agent) -> list[McpServerSettings]:
    ids = agent_store.list_mcp_servers_for_agent(agent.id)
    servers: list[McpServerSettings] = []
    for server_id in ids:
        row = mcp_server_store.get_mcp_server(
            agent.id, server_id
        ) or mcp_server_store.get_mcp_server(None, server_id)
        if row is None:
            continue
        raw_auth_config = row.get("auth_config")
        if raw_auth_config is None and row.get("api_key_env"):
            raw_auth_config = {"key_env": row["api_key_env"]}
        auth_config = parse_mcp_auth_config(row.get("auth_type"), raw_auth_config)
        api_key_env = ""
        auth = None
        auth_type = "none"
        header_style = "bearer"
        credential_input = "form"
        if isinstance(auth_config, ApiKeyMcpAuthConfig):
            auth_type = "api_key"
            api_key_env = auth_config.key_env
        elif isinstance(auth_config, OAuthClientCredentialsMcpAuthConfig):
            auth_type = "oauth_client_credentials"
            auth = auth_config
        elif isinstance(auth_config, OAuthAuthorizationCodeMcpAuthConfig):
            auth_type = "oauth_authorization_code"
            auth = auth_config
        elif isinstance(auth_config, ApiKeyPerUserMcpAuthConfig):
            auth_type = "api_key_per_user"
            header_style = auth_config.header_style
            credential_input = auth_config.credential_input
        servers.append(
            McpServerSettings(
                id=server_id,
                transport=row["transport"],
                url=row["url"],
                auth_type=auth_type,
                api_key_env=api_key_env,
                command=row["command"],
                args=row["args"] or [],
                env=row["env"] or {},
                headers=row["headers"] or {},
                auth=auth,
                header_style=header_style,
                credential_input=credential_input,
                degrade_mode=row.get("degrade_mode") or "degrade",
                file_root=row.get("file_root") or "",
                file_isolation=row.get("file_isolation") or "on",
                approval_rules=[
                    McpApprovalRule(**rule) for rule in (row.get("approval_rules") or [])
                ],
            )
        )
    return servers


def _mcp_payload_to_map(payload: dict[str, Any]) -> None:
    """Rewrite a dumped AgentFile payload's ``mcp_servers`` list into the standard
    ``mcpServers`` map (key = server id), hoisting non-default fleetent fields under each
    entry's ``x-fleetent`` block. In place; no-op when there are no MCP servers."""
    servers = payload.pop("mcp_servers", None)
    if not servers:
        return
    mapping: dict[str, Any] = {}
    for entry in servers:
        entry = dict(entry)
        sid = entry.pop("id")
        ext = {}
        for key, default in MCP_FLEETENT_EXT_DEFAULTS.items():
            value = entry.pop(key, default)
            if value != default:
                ext[key] = value
        if ext:
            entry["x-fleetent"] = ext
        mapping[sid] = entry
    payload["mcpServers"] = mapping


def _knowledge_for_agent(agent: agent_store.Agent) -> AgentKnowledge:
    try:
        kb_ids = agent_kbs_store.list_kbs_for_agent(agent.tenant_id, agent.id)
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


def home_dir(name: str, tenant_id: str | None = None) -> Path:
    """Resolve an agent home under tenant-first layout.

    When ``tenant_id`` is omitted, prefer the DB-authored tenant for ``name`` and
    fall back to the default-tenant shim for standalone compatibility.
    """
    resolved_tenant = tenant_id
    if resolved_tenant is None:
        try:
            agent = agent_store.get_by_name(name)
        except sqlite3.OperationalError as exc:
            if "no such table: agents" not in str(exc):
                raise
            agent = None
        resolved_tenant = agent.tenant_id if agent is not None else "default"
    return paths.tenant_agent_home_dir(resolved_tenant, name)


def _env_var_names(agent: AgentFile) -> list[str]:
    """Collect the env-var names the agent's home references (delegates to shared collector)."""
    return collect_env_var_names(agent)


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
    return provider_admin_store.provider_key_for_env(env_name)


def _parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, val = stripped.split("=", 1)
        values[key.strip()] = val
    return values


def _ensure_managed_tui_token(existing: dict[str, str], *, agent_id: int | None) -> str | None:
    """Return a managed agent's TUI token, persisting it through the secret store."""
    if agent_id is None:
        return None
    if secret_store.status(agent_id, _TUI_TOKEN_ENV) == "set":
        stored = secret_store.get_decrypted(agent_id, _TUI_TOKEN_ENV)
        if stored:
            return stored
    token = existing.get(_TUI_TOKEN_ENV, "") or f"ma-{secrets.token_hex(32)}"
    with contextlib.suppress(secret_store.SecretKeyError):
        secret_store.set(agent_id, _TUI_TOKEN_ENV, token, "materialize")
    return token


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
    managed_tui_token = _ensure_managed_tui_token(
        existing,
        agent_id=source_agent.id if source_agent is not None else None,
    )
    slots_by_env = (
        {slot.env_name: slot for slot in credential_slots.list_slots(source_agent)}
        if source_agent is not None
        else {}
    )
    lines: list[str] = []
    for name in names:
        slot = slots_by_env.get(name)
        if source_agent is not None:
            # real materialize (secret/provider tables exist): operator host value →
            # provider inline key → shared secret (e.g. KB token). status() needs no key.
            shared = (
                secret_store.get_decrypted(None, name)
                if secret_store.status(None, name) == "set"
                else ""
            )
            if (
                slot is not None
                and slot.mode == "inject"
                and secret_store.status(source_agent.id, name) == "set"
            ):
                value = secret_store.get_decrypted(source_agent.id, name)
            elif slot is not None and slot.mode == "inject":
                value = (_provider_key_for_env(name) or "") or shared
            else:
                value = existing.get(name, "") or (_provider_key_for_env(name) or "") or shared
        else:
            # bare write_home (no store context): keep the operator value, never touch tables
            value = existing.get(name, "")
        lines.append(f"{name}={value}")
    if managed_tui_token:
        lines.append(f"{_TUI_TOKEN_ENV}={managed_tui_token}")
    # keep any operator-added vars not referenced by the definition
    excluded = exclude_existing or set()
    for key, val in existing.items():
        if key in excluded:
            continue
        if key != _TUI_TOKEN_ENV and key not in names:
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
            _logger.warn("rematerialize_failed", agent=name, exception=exc)
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
    tenant_id = source_agent.tenant_id if source_agent is not None else None
    home = home_dir(agent.name, tenant_id)
    home.mkdir(parents=True, exist_ok=True)
    _logger.debug("agent_home_write_start", name=agent.name, path=str(home))
    (home / "data").mkdir(parents=True, exist_ok=True)
    payload = agent.model_dump(mode="json", exclude_defaults=False)
    _mcp_payload_to_map(payload)  # render MCP servers in the standard mcpServers map form
    (home / AGENT_FILE_NAME).write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    _seed_env(
        home,
        _env_var_names(agent),
        source_agent=source_agent,
        exclude_existing=_knowledge_env_var_names(knowledge_config),
    )
    _copy_skills(home, source_agent=source_agent)
    return home


def _skill_dir_version(skill_dir: Path) -> str:
    """Stable content hash for one skill directory (excludes .git)."""
    digest = sha256()
    for path in sorted(p for p in skill_dir.rglob("*") if p.is_file() and ".git" not in p.parts):
        digest.update(path.relative_to(skill_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _skill_has_runtime_provenance(skill_dir: Path) -> bool:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return False
    frontmatter: dict[str, Any] = (
        skill_registry._parse_frontmatter(skill_md.read_text(encoding="utf-8")) or {}
    )
    return bool(frontmatter.get("proposal_id") or frontmatter.get("applied_at"))


def _is_skill_drifted(
    *,
    agent_id: int,
    skill_name: str,
    src_skill_dir: Path,
    dest_skill_dir: Path,
) -> bool:
    if not dest_skill_dir.exists():
        return False
    if _skill_has_runtime_provenance(dest_skill_dir):
        return True
    state = skill_admin_store.get_drift(agent_id, skill_name)
    home_hash = _skill_dir_version(dest_skill_dir)
    base_version = state["base_version"]

    if isinstance(base_version, str) and base_version:
        # base_version is always a content hash (sha256 of materialized skill dir).
        # Drift = agent modified their home copy from what was last materialized.
        return home_hash != base_version

    # No base_version recorded — fall back to comparing home vs current pool.
    return home_hash != _skill_dir_version(src_skill_dir)


def _copy_skills(home: Path, *, source_agent: agent_store.Agent | None = None) -> None:
    """Mirror the platform's global skills dir into ``<home>/skills/``.

    Makes the agent home self-contained (the agent process reads only its own home).
    Full copy: visibility is later narrowed at runtime by agent.yaml's allowed_skills /
    disabled_skills. Excludes ``.git`` so it is never copied into an agent home.
    Best-effort: a missing source is skipped; a copy error is logged but never aborts
    materialize (agent.yaml is already written).
    """
    src = Path(skill_registry._resolve_skills_dir(None))
    if not src.exists():
        return
    dest_root = home / "skills"
    dest_root.mkdir(parents=True, exist_ok=True)

    # Skip .git — it belongs to the pool repo, not to individual skill dirs
    for skill_dir in sorted(p for p in src.iterdir() if p.is_dir() and p.name != ".git"):
        dest_skill_dir = dest_root / skill_dir.name
        try:
            if source_agent is not None:
                drifted = _is_skill_drifted(
                    agent_id=source_agent.id,
                    skill_name=skill_dir.name,
                    src_skill_dir=skill_dir,
                    dest_skill_dir=dest_skill_dir,
                )
                skill_admin_store.set_drift(source_agent.id, skill_dir.name, drifted=drifted)
                if drifted:
                    _logger.info(
                        "agent_home_skill_copy_skipped_drift",
                        agent=source_agent.name,
                        skill=skill_dir.name,
                        path=str(dest_skill_dir),
                    )
                    continue

            if dest_skill_dir.exists():
                shutil.rmtree(dest_skill_dir)
            shutil.copytree(skill_dir, dest_skill_dir)

            if source_agent is not None:
                # Always store content hash as base_version for drift detection.
                # Pool git sha is read from the catalog's current_version (recorded once at
                # sync/publish time) — never walk git history per skill here (a large-mirror
                # walk is what saturated the desired-state hot path in production).
                new_base = _skill_dir_version(skill_dir)
                new_base_commit = skill_admin_store.get_source(skill_dir.name).get(
                    "current_version"
                )
                skill_admin_store.set_base_version(source_agent.id, skill_dir.name, new_base)
                skill_admin_store.set_base_commit(source_agent.id, skill_dir.name, new_base_commit)
                skill_admin_store.set_drift(source_agent.id, skill_dir.name, drifted=False)
        except OSError as exc:
            _logger.warn("agent_home_skill_copy_failed", path=str(skill_dir), exception=exc)
