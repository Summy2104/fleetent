"""Integration tests for agent_app.py /chat allowed_tools semantics.

Verifies that the /chat route converts empty allowed_tools list to None,
so the tool filter is skipped and all tools remain accessible.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import yaml
from fastapi.testclient import TestClient

import fleetent.runtime.loop as loop_mod
from fleetent import agent_config, user_store
from fleetent.runtime import agent_app


def _write_agent(agents_dir, name, allowed_tools):
    doc = {
        "name": name,
        "version": 1,
        "models": agent_config.default_models().model_dump(),
        "access": {"allow_users": ["U1"]},
        "allowed_tools": allowed_tools,
    }
    d = agents_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def _make_client(monkeypatch, agent_name, captured):
    async def fake_run_stream(message, **kwargs):
        captured["allowed_tools"] = kwargs.get("allowed_tools", "NOT_SET")
        yield '{"type":"text","content":"ok"}'

    monkeypatch.setattr(loop_mod, "run_stream", fake_run_stream)

    fake_user = MagicMock(spec=user_store.User)
    fake_user.id = "U1"
    monkeypatch.setattr(user_store, "authenticate", lambda _token: (fake_user, {}))

    app = agent_app.build_app(agent_name)
    return TestClient(app, raise_server_exceptions=True)


def test_chat_empty_allowed_tools_passes_none(monkeypatch, tmp_path):
    """build_app() /chat: agent with allowed_tools=[] → kwargs['allowed_tools'] is None."""
    agents_dir = tmp_path / "agents"
    _write_agent(agents_dir, "mybot", allowed_tools=[])
    agent_config.scan(agents_dir)

    captured: dict = {}
    client = _make_client(monkeypatch, "mybot", captured)

    resp = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"Authorization": "Bearer ma-test"},
    )

    assert resp.status_code == 200
    assert captured["allowed_tools"] is None, (
        f"Expected None but got {captured['allowed_tools']!r}; "
        "empty allowed_tools should allow all tools"
    )


def test_chat_nonempty_allowed_tools_passes_list(monkeypatch, tmp_path):
    """build_app() /chat: agent with allowed_tools=['web_search'] → kwargs keeps the list."""
    agents_dir = tmp_path / "agents"
    _write_agent(agents_dir, "mybot", allowed_tools=["web_search"])
    agent_config.scan(agents_dir)

    captured: dict = {}
    client = _make_client(monkeypatch, "mybot", captured)

    resp = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"Authorization": "Bearer ma-test"},
    )

    assert resp.status_code == 200
    assert captured["allowed_tools"] == ["web_search"]
