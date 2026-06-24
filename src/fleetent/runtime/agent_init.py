"""Scaffold a runnable agent home from a built-in template (`fleetent agent init`).

Pure local scaffolding: no platform service and no database. Writes a self-contained
``<home>/agent.yaml`` (its ``name`` set to the agent id, so ``fleetent agent run <id>``'s
directory-name check passes) plus a ``.env`` listing the env-var names the agent
references (empty values, never real secrets). The template is embedded here — the
installed global command has no repo working tree to read repository example templates.
"""

from __future__ import annotations

import secrets as secrets_module
from collections.abc import Iterable
from pathlib import Path

import yaml

from fleetent.agent_config import (
    AgentFile,
    AgentModels,
    ModelRouteEntry,
    ModelTarget,
    collect_env_var_names,
)
from fleetent.runtime.agent_app import resolve_home


def _template_agent(agent_id: str) -> AgentFile:
    """A minimal, valid starter agent definition (core fields only; no intelligence)."""
    return AgentFile(
        name=agent_id,
        version=1,
        system_prompt="You are a helpful assistant.\n",
        models=AgentModels(
            targets=[
                ModelTarget(
                    id="primary",
                    provider="anthropic",
                    protocol="openai_chat",
                    base_url="https://api.anthropic.com/v1/",
                    model="claude-opus-4-8",
                    api_key_env="FLEETENT_MODEL_PRIMARY_API_KEY",
                    max_tokens=4096,
                )
            ],
            routes={"default": [ModelRouteEntry(target="primary")]},
        ),
        allowed_tools=["search_*", "read_skill"],
    )


def referenced_env_names(agent: AgentFile) -> list[str]:
    """Return env-var names the agent references.

    Thin re-export of the shared collector in agent_config so callers don't
    need a second import. The shared collector uses flatten-all-*_env and catches
    every field (embedding, rerank, telegram, MCP, etc.) without manual enumeration.
    """
    return collect_env_var_names(agent)


def ensure_env_scaffold(
    home_dir: Path,
    *,
    referenced_env_names: Iterable[str] = (),
    secrets: dict[str, str] | None = None,
) -> None:
    """Write a complete .env (0600) for the agent home.

    Always rewrites the file with the full set of referenced env-var names:
    - Names present in ``secrets`` get their real value written.
    - Names absent from ``secrets`` get an empty placeholder.
    - FLEETENT_TUI_TOKEN is preserved from an existing .env or generated fresh.

    The file is always written at mode 0600 and the home dir at 0700.
    """
    env_path = home_dir / ".env"
    home_dir.mkdir(parents=True, exist_ok=True)
    home_dir.chmod(0o700)

    # Preserve existing TUI token if present; generate a new one otherwise.
    existing_token = ""
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("FLEETENT_TUI_TOKEN="):
                existing_token = line.partition("=")[2]
                break
    tui_token = existing_token or f"ma-{secrets_module.token_hex(32)}"

    resolved_secrets = secrets or {}
    names = sorted(set(referenced_env_names))
    lines: list[str] = []
    for name in names:
        value = resolved_secrets.get(name, "")
        lines.append(f"{name}={value}")
    lines.append(f"FLEETENT_TUI_TOKEN={tui_token}")

    content = "\n".join(lines) + "\n" if lines else ""
    env_path.write_text(content, encoding="utf-8")
    env_path.chmod(0o600)


def scaffold_agent_home(
    agent_id: str, home: str | Path | None = None, *, force: bool = False
) -> Path:
    """Scaffold a runnable agent home and return its directory.

    home = ``home`` if given else ``FLEETENT_HOME/tenants/default/agents/<agent_id>`` (same
    resolution as ``fleetent agent run``). Refuses to overwrite an existing ``agent.yaml``
    unless ``force``; an existing ``.env`` is always preserved.
    """
    home_dir = Path(home) if home is not None else resolve_home(agent_id)
    agent_yaml = home_dir / "agent.yaml"
    if agent_yaml.exists() and not force:
        raise FileExistsError(f"{agent_yaml} already exists; use --force to overwrite")

    agent = _template_agent(agent_id)
    home_dir.mkdir(parents=True, exist_ok=True)
    agent_yaml.write_text(
        yaml.safe_dump(agent.model_dump(), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    ensure_env_scaffold(home_dir, referenced_env_names=referenced_env_names(agent))

    return home_dir
