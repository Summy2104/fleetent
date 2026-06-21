"""Integration tests for agent_app.py /chat allowed_tools semantics.

Verifies that the /chat route converts empty allowed_tools list to None,
so the tool filter is skipped and all tools remain accessible.
"""

from __future__ import annotations

import yaml
from fastapi.testclient import TestClient

import fleetent.runtime.loop as loop_mod
from fleetent import agent_config
from fleetent.identity import Principal
from fleetent.runtime import agent_app


def _write_agent(agents_dir, name, allowed_tools):
    doc = {
        "name": name,
        "version": 1,
        "models": agent_config.default_models().model_dump(),
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
    monkeypatch.setattr(
        agent_app.LocalBearerAdapter,
        "__call__",
        lambda self, _token: Principal(user_id="U1", tenant_id="default"),
    )

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


def test_chat_accepts_tui_token_when_local_api_key_auth_missing(monkeypatch, tmp_path):
    """Managed-agent ingress uses FLEETENT_TUI_TOKEN for /chat, not local api_keys."""
    agents_dir = tmp_path / "agents"
    _write_agent(agents_dir, "mybot", allowed_tools=[])
    agent_config.scan(agents_dir)
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", "ma-chat-token")

    captured: dict = {}

    async def fake_run_stream(message, **kwargs):
        captured["principal"] = kwargs.get("principal")
        yield '{"type":"text","content":"ok"}'

    monkeypatch.setattr(loop_mod, "run_stream", fake_run_stream)
    monkeypatch.setattr(agent_app.LocalBearerAdapter, "__call__", lambda self, _token: None)

    client = TestClient(agent_app.build_app("mybot"), raise_server_exceptions=True)

    ok = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"Authorization": "Bearer ma-chat-token"},
    )
    rejected = client.post(
        "/chat",
        json={"message": "hi"},
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert ok.status_code == 200
    assert captured["principal"] == Principal(user_id="local", tenant_id="default")
    assert rejected.status_code == 401
