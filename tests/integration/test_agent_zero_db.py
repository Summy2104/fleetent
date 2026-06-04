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


def _write_agent(root) -> None:
    d = root / "support"
    d.mkdir(parents=True)
    (d / "agent.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "support",
                "version": 1,
                "system_prompt": "S",
                "allowed_tools": ["shell"],
                "mcp_servers": [{"id": "acme", "transport": "http", "url": "https://acme"}],
                "bindings": {"channels": ["slack:C1"], "users": ["u1"], "default": True},
            }
        ),
        encoding="utf-8",
    )


def test_runtime_resolution_does_not_touch_db(tmp_path, monkeypatch):
    _write_agent(tmp_path)
    agent_config.scan(tmp_path)
    # Any real sqlite connection now raises — proves the path below is DB-free.
    monkeypatch.setattr(db.sqlite3, "connect", _boom)

    snap = snapshot.resolve_agent_for_request("slack", "C1", "u1")
    assert snap is not None and snap.name == "support"
    assert snapshot.connector_scope(snap) == "support"

    resolved = {
        s["id"]
        for s in snapshot.resolve_mcp_servers(
            snap, [{"id": "default", "transport": "http", "url": "https://d"}]
        )
    }
    assert resolved == {"acme", "default"}

    agent = normalizer.get_agent_for_context("slack", "C1", "u1")
    assert agent is not None and agent.name == "support"
    assert agent.system_prompt == "S"
