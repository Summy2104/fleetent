"""File-driven agent configuration: self-contained `agent.yaml` per agent.

Each agent lives at ``<agents_dir>/<name>/agent.yaml`` and fully describes the agent
(definition, capability switches, inline MCP servers, and channel/user bindings). This
module parses and validates those files and builds the in-memory index the runtime
uses to resolve agents and route requests — with zero database access. The DB and
admin console remain the authoring source of truth; these files are generated artifacts
(see openspec change ``file-driven-agent-config``).
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from fleetent.config import McpServerSettings
from fleetent.platform.config_validation import _flatten, _looks_inline_secret

# Agents root directory. Module-level constant (injectable via monkeypatch per the
# project's no-global-mutable-state rule); env override mirrors FLEETENT_SKILLS_DIR.
AGENTS_DIR = Path("config/agents")

AGENT_FILE_NAME = "agent.yaml"


class AgentBindings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default: bool = False
    channels: list[str] = Field(default_factory=list)
    users: list[str] = Field(default_factory=list)


class AgentFile(BaseModel):
    """Schema for a self-contained ``agent.yaml``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    version: int
    tenant_id: str = "default"
    team_id: str | None = None
    system_prompt: str = ""
    model_overrides: dict[str, Any] = Field(default_factory=dict)
    memory_namespace: str = ""
    skills_dir: str | None = None
    allowed_skills: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
    features: dict[str, Any] = Field(default_factory=dict)
    mcp_servers: list[McpServerSettings] = Field(default_factory=list)
    bindings: AgentBindings = Field(default_factory=AgentBindings)


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
    payload = {"mcp_servers": [server.model_dump() for server in agent.mcp_servers]}
    for key, value in _flatten(payload):
        if isinstance(value, str) and _looks_inline_secret(value):
            raise ValueError(
                f"inline secret-like value in agent '{agent.name}' at '{key}' ({path}); "
                "reference secrets by environment-variable name instead"
            )


def build_index(agents_dir: str | Path | None = None) -> AgentConfigIndex:
    """Scan the agents directory and build a fresh resolution index (pure; no globals)."""
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


def current() -> AgentConfigIndex:
    """Return the currently published index."""
    return _index
