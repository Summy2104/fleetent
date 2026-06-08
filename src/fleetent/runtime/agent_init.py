"""Scaffold a runnable agent home from a built-in template (`fleetent agent init`).

Pure local scaffolding: no platform service and no database. Writes a self-contained
``<home>/agent.yaml`` (its ``name`` set to the agent id, so ``fleetent agent run <id>``'s
directory-name check passes) plus a ``.env`` listing the env-var names the agent
references (empty values, never real secrets). The template is embedded here — the
installed global command has no repo working tree to read repository example templates.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import yaml

from fleetent.agent_config import AgentFile, AgentModels, ModelRouteEntry, ModelTarget
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


def _referenced_env_names(agent: AgentFile) -> list[str]:
    """Collect env-var names the agent references (always + MCP/connector ``*_env``)."""
    names: set[str] = set()
    for target in agent.models.targets:
        if target.api_key_env:
            names.add(target.api_key_env)
    for server in agent.mcp_servers:
        for attr in ("api_key_env", "client_secret_env"):
            value = getattr(server, attr, "")
            if value:
                names.add(value)
    slack = agent.connectors.slack
    if slack is not None:
        names.update(n for n in (slack.bot_token_env, slack.app_token_env) if n)
    return sorted(names)


def scaffold_agent_home(
    agent_id: str, home: str | Path | None = None, *, force: bool = False
) -> Path:
    """Scaffold a runnable agent home and return its directory.

    home = ``home`` if given else ``FLEETENT_HOME/agents/<agent_id>`` (same resolution as
    ``fleetent agent run``). Refuses to overwrite an existing ``agent.yaml`` unless
    ``force``; an existing ``.env`` is always preserved.
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

    env_path = home_dir / ".env"
    if not env_path.exists():
        tui_token = f"ma-{secrets.token_hex(32)}"
        body = "".join(f"{name}=\n" for name in _referenced_env_names(agent))
        body += f"FLEETENT_TUI_TOKEN={tui_token}\n"
        env_path.write_text(body, encoding="utf-8")

    return home_dir
