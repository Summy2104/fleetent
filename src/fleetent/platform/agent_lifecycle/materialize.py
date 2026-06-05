"""Materialize a runnable agent home from an authored definition (DB→file export).

The platform authors agents; this writes each agent's self-contained home —
``FLEETENT_HOME/<name>/agent.yaml`` (the full home schema) plus a ``.env`` scaffold that
references secrets by env-var name only (never plaintext) — so the agent is runnable by
``fleetent agent run`` (see openspec change ``platform-agent-lifecycle``).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from fleetent import agent_store, paths
from fleetent.agent_config import AGENT_FILE_NAME, AgentFile, default_models
from fleetent.intelligence.knowledge_base.config import KnowledgeConfigSnapshot
from fleetent.platform.config_validation import _flatten


def agent_file_from_store(agent: agent_store.Agent) -> AgentFile:
    """Build the home schema from the authored core definition.

    connectors/access are not yet stored per-agent on the platform; they materialize as
    their safe defaults (no connectors; default-closed access) until authoring lands.
    """
    return AgentFile(
        name=agent.name,
        version=1,
        system_prompt=agent.system_prompt,
        allowed_tools=agent.allowed_tools,
        allowed_skills=agent.allowed_skills,
        plugins=agent.plugins,
        features=agent.features,
        models=default_models(),
        memory_namespace=agent.memory_namespace,
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
