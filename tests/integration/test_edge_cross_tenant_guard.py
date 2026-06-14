"""Integration: edge cross-tenant access guard on /chat and /ws (cross-tenant-access-guard).

Requester Principal.tenant_id must match the target agent's deployment tenant
(agent_tenant, from agent.yaml). Mismatch is default-closed rejected before the agent
runs (HTTP 403 / WS close); same-tenant passes through unchanged (single-tenant no-op).
"""

from __future__ import annotations

import json

import pytest
import yaml
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import fleetent.runtime.loop as loop_mod
from fleetent import agent_config
from fleetent.identity import Principal
from fleetent.runtime import agent_app

_TUI_TOKEN = "tui-test-token"


def _write_agent(agents_dir, name, tenant_id):
    doc = {
        "name": name,
        "version": 1,
        "models": agent_config.default_models().model_dump(),
        "tenant_id": tenant_id,
    }
    d = agents_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def _patch_run_stream(monkeypatch, captured):
    async def fake_run_stream(message, **kwargs):
        captured["called"] = True
        captured["principal"] = kwargs.get("principal", "NOT_SET")
        yield '{"type":"text","content":"ok"}'

    monkeypatch.setattr(loop_mod, "run_stream", fake_run_stream)


def _patch_requester_tenant(monkeypatch, tenant_id):
    monkeypatch.setattr(
        agent_app.LocalBearerAdapter,
        "__call__",
        lambda self, _token: Principal(user_id="U1", tenant_id=tenant_id),
    )


# --- /chat (task 1.1 / 1.2) ---------------------------------------------------


def test_chat_cross_tenant_rejected(monkeypatch, tmp_path):
    """Requester tenant T1 vs agent tenant T2 → 403, run never reaches T2 data."""
    agents_dir = tmp_path / "agents"
    _write_agent(agents_dir, "bot", tenant_id="T2")
    agent_config.scan(agents_dir)

    captured: dict = {}
    _patch_run_stream(monkeypatch, captured)
    _patch_requester_tenant(monkeypatch, "T1")

    client = TestClient(agent_app.build_app("bot"), raise_server_exceptions=True)
    resp = client.post("/chat", json={"message": "hi"}, headers={"Authorization": "Bearer ma-test"})

    assert resp.status_code == 403
    assert "called" not in captured, "run_stream must not run for a cross-tenant request"


def test_chat_same_tenant_allowed(monkeypatch, tmp_path):
    """Same tenant (default/default) → agent runs as before (guard is a no-op)."""
    agents_dir = tmp_path / "agents"
    _write_agent(agents_dir, "bot", tenant_id="default")
    agent_config.scan(agents_dir)

    captured: dict = {}
    _patch_run_stream(monkeypatch, captured)
    _patch_requester_tenant(monkeypatch, "default")

    client = TestClient(agent_app.build_app("bot"), raise_server_exceptions=True)
    resp = client.post("/chat", json={"message": "hi"}, headers={"Authorization": "Bearer ma-test"})

    assert resp.status_code == 200
    assert captured.get("called") is True


# --- /ws (task 1.1 / 1.2) -----------------------------------------------------


def test_ws_cross_tenant_rejected(monkeypatch, tmp_path):
    """TUI principal tenant 'default' vs agent tenant T2 → connection closed."""
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", _TUI_TOKEN)
    agents_dir = tmp_path / "agents"
    _write_agent(agents_dir, "bot", tenant_id="T2")
    agent_config.scan(agents_dir)

    app = agent_app.build_app("bot")
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws", headers={"Authorization": f"Bearer {_TUI_TOKEN}"}) as ws,
    ):
        ws.receive_text()


def test_ws_same_tenant_allowed(monkeypatch, tmp_path):
    """Same tenant (default/default) → handshake completes (gateway.ready)."""
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", _TUI_TOKEN)
    agents_dir = tmp_path / "agents"
    _write_agent(agents_dir, "bot", tenant_id="default")
    agent_config.scan(agents_dir)

    app = agent_app.build_app("bot")
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws", headers={"Authorization": f"Bearer {_TUI_TOKEN}"}) as ws,
    ):
        frame = json.loads(ws.receive_text())

    assert frame["method"] == "event"
    assert frame["params"]["type"] == "gateway.ready"
