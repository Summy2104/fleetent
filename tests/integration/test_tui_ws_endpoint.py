"""WebSocket gateway /ws: handshake, auth, parse error, SSE coexistence (tui-gateway 5.1)."""

import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import fleetent.user_store as us


@pytest.fixture
def app_and_user(tmp_path, monkeypatch):
    monkeypatch.setattr(us, "DB_PATH", tmp_path / "users.db")
    import fleetent.server as srv

    # IM connectors are driven by the manager at startup; stub it out for the test.
    monkeypatch.setattr(srv._connector_manager, "start_all_enabled", AsyncMock())
    monkeypatch.setattr(srv._connector_manager, "stop", AsyncMock())
    user = us.create_user("WSUser")
    return srv.app, user


def test_ws_ready_on_valid_key(app_and_user):
    app, user = app_and_user
    with TestClient(app) as client, client.websocket_connect(
        "/ws", headers={"Authorization": f"Bearer {user.api_key}"}
    ) as ws:
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
    with TestClient(app) as client, client.websocket_connect(
        "/ws", headers={"Authorization": f"Bearer {user.api_key}"}
    ) as ws:
        json.loads(ws.receive_text())  # gateway.ready
        ws.send_text("this is not json{")
        err = json.loads(ws.receive_text())
        assert err["error"]["code"] == -32700
        # connection still usable: an unknown method gets a normal error response
        ws.send_text(json.dumps({"id": 1, "method": "frobnicate", "params": {}}))
        resp = json.loads(ws.receive_text())
        assert resp["id"] == 1 and resp["error"]["code"] == -32601


def test_sse_chat_route_unaffected(app_and_user):
    app, _user = app_and_user
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/chat" in paths  # existing SSE endpoint still mounted
    assert "/ws" in paths  # new gateway mounted
