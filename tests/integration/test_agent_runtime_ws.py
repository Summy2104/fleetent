"""Agent-runtime WebSocket gateway /ws: handshake, auth, parse error (tui-gateway 5.1).

The /ws behavior moved from the platform app to the standalone agent runtime
(`fleetent.runtime.agent_app.build_app`). Auth (Bearer ma- key via
user_store.authenticate) and the tui dispatch/protocol are identical.
"""

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import fleetent.user_store as us
from fleetent.runtime import agent_app


@pytest.fixture
def app_and_user(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    user = us.create_user("WSUser")
    return agent_app.build_app("some-agent"), user


def test_ws_ready_on_valid_key(app_and_user):
    app, user = app_and_user
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws", headers={"Authorization": f"Bearer {user.api_key}"}) as ws,
    ):
        frame = json.loads(ws.receive_text())
    assert frame["method"] == "event"
    assert frame["params"]["type"] == "gateway.ready"


def test_ws_invalid_key_rejected(app_and_user):
    app, _user = app_and_user
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws", headers={"Authorization": "Bearer ma-bogus"}) as ws,
    ):
        ws.receive_text()


def test_ws_missing_key_rejected(app_and_user):
    app, _user = app_and_user
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws") as ws,
    ):
        ws.receive_text()


def test_ws_bad_json_frame_returns_parse_error_without_closing(app_and_user):
    app, user = app_and_user
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws", headers={"Authorization": f"Bearer {user.api_key}"}) as ws,
    ):
        json.loads(ws.receive_text())  # gateway.ready
        ws.send_text("this is not json{")
        err = json.loads(ws.receive_text())
        assert err["error"]["code"] == -32700
        # connection still usable: an unknown method gets a normal error response
        ws.send_text(json.dumps({"id": 1, "method": "frobnicate", "params": {}}))
        resp = json.loads(ws.receive_text())
        assert resp["id"] == 1 and resp["error"]["code"] == -32601
