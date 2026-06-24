"""Runtime agent resolution touches no database (file-driven-agent-config §5.2).

Rigs the lowest-level sqlite connection to raise, then proves file-based resolution,
inline-MCP overlay, connector scope, and the IM routing entry all succeed.
"""

import yaml

import fleetent.db as db
from fleetent import agent_config
from fleetent.im_gateway import normalizer
from fleetent.runtime import snapshot


def _boom(*args, **kwargs):
    raise AssertionError("database accessed on the zero-DB runtime path")


def _write_agent(home) -> None:
    # Deployed single-agent home layout: tenants/default/agents/default/agent.yaml is the forced
    # default (bindings were removed from AgentFile; resolution is default-only).
    d = home / "tenants" / "default" / "agents" / "default"
    d.mkdir(parents=True)
    (d / "agent.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "default",
                "version": 1,
                "system_prompt": "S",
                "models": agent_config.default_models().model_dump(mode="json"),
                "allowed_tools": ["shell"],
                "mcpServers": {"acme": {"transport": "http", "url": "https://acme"}},
            }
        ),
        encoding="utf-8",
    )


def test_runtime_resolution_does_not_touch_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    _write_agent(tmp_path)
    agent_config.scan()
    # Any real sqlite connection now raises — proves the path below is DB-free.
    monkeypatch.setattr(db.sqlite3, "connect", _boom)

    snap = snapshot.resolve_agent_for_request("slack", "C1", "u1")
    assert snap is not None and snap.name == "default"
    assert snapshot.connector_scope(snap) == "default"

    resolved = {
        s["id"]
        for s in snapshot.resolve_mcp_servers(
            snap, [{"id": "default", "transport": "http", "url": "https://d"}]
        )
    }
    assert resolved == {"acme", "default"}

    agent = normalizer.get_agent_for_context()
    assert agent is not None and agent.name == "default"
    assert agent.system_prompt == "S"
