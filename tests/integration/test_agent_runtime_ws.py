"""Agent-runtime WebSocket gateway /ws: handshake, auth, parse error (tui-gateway 5.1).

The /ws behavior lives in the standalone agent runtime
(`fleetent.runtime.agent_app.build_app`). Auth is the agent-local
FLEETENT_TUI_TOKEN bearer (tui-agent-auth) — no platform user_store involved.
"""

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from fleetent.runtime import agent_app

_TOKEN = "tui-test-token"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", _TOKEN)
    return agent_app.build_app("some-agent")


def test_ws_ready_on_valid_key(app):
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws", headers={"Authorization": f"Bearer {_TOKEN}"}) as ws,
    ):
        frame = json.loads(ws.receive_text())
    assert frame["method"] == "event"
    assert frame["params"]["type"] == "gateway.ready"


def test_ws_invalid_key_rejected(app):
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws", headers={"Authorization": "Bearer wrong-token"}) as ws,
    ):
        ws.receive_text()


def test_ws_missing_key_rejected(app):
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws") as ws,
    ):
        ws.receive_text()


def test_ws_bad_json_frame_returns_parse_error_without_closing(app):
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws", headers={"Authorization": f"Bearer {_TOKEN}"}) as ws,
    ):
        json.loads(ws.receive_text())  # gateway.ready
        ws.send_text("this is not json{")
        err = json.loads(ws.receive_text())
        assert err["error"]["code"] == -32700
        # connection still usable: an unknown method gets a normal error response
        ws.send_text(json.dumps({"id": 1, "method": "frobnicate", "params": {}}))
        resp = json.loads(ws.receive_text())
        assert resp["id"] == 1 and resp["error"]["code"] == -32601
