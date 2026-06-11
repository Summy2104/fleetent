"""Integration: TUI /ws carries the resolved Principal end-to-end (task 3).

After a bearer handshake the dispatch layer must hand run_stream the full Principal
(with tenant_id), not a bare user_id string — so the run is never principal-less on the
authenticated edge path.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import fleetent.tui.dispatch as dispatch
from fleetent.identity import Principal
from fleetent.runtime import agent_app

_TUI_TOKEN = "tui-test-token"


def test_ws_run_stream_receives_principal(monkeypatch):
    monkeypatch.setenv("FLEETENT_TUI_TOKEN", _TUI_TOKEN)

    captured: dict = {}

    async def fake_run_stream(user_input, principal=None, **kwargs):
        captured["principal"] = principal
        yield {"type": "done", "content": "ok"}

    monkeypatch.setattr(dispatch, "run_stream", fake_run_stream)

    app = agent_app.build_app("some-agent")
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws", headers={"Authorization": f"Bearer {_TUI_TOKEN}"}) as ws,
    ):
        json.loads(ws.receive_text())  # gateway.ready
        ws.send_text(json.dumps({"id": 1, "method": "send", "params": {"message": "hi"}}))
        # Drain frames until the run's terminal `done` event arrives.
        for _ in range(10):
            frame = json.loads(ws.receive_text())
            if frame.get("method") == "event" and frame["params"].get("type") == "done":
                break

    assert isinstance(captured.get("principal"), Principal)
    assert captured["principal"] == Principal(user_id="local", tenant_id="default")
