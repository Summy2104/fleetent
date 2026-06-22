"""Tests for chat_admin_api (/admin/sessions). Covers scenarios 100-102.

agent-runtime / session / im-gateway seams are monkeypatched so the tests exercise
the management behaviour (takeover, guards, audit, session governance).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.agent_store as agent_store
import fleetent.auth as auth
import fleetent.platform.chat_management.chat_admin_api as api
import fleetent.platform.chat_management.session_admin_store as store
import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    agent_store.create_agent("ops", "Ops.", ["shell"])
    agent_store.create_agent("qa", "QA.", ["shell"])
    monkeypatch.setattr(api, "load_transcript", lambda sid: [])
    monkeypatch.setattr(api, "clear_session", lambda sid: None)
    monkeypatch.setattr(api, "inject", lambda sid, role, content: None)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str, confirm: bool = False) -> dict:
    h = {"Authorization": f"Session {token}"}
    if confirm:
        h["X-Confirm"] = "true"
    return h


def test_playground_routes_removed(client):
    token, _ = _session_for("admin")
    assert (
        client.post(
            "/admin/chat/start", headers=_hdr(token), json={"agent_name": "ops"}
        ).status_code
        == 404
    )
    assert client.get("/admin/chat/sessions", headers=_hdr(token)).status_code == 404
    assert client.get("/admin/sessions", headers=_hdr(token)).status_code == 200


# --- session governance (场景 100/101/102) -----------------------------------


def test_takeover_inject_release(client, monkeypatch):  # 场景 100
    injected = []
    delivered = []
    monkeypatch.setattr(
        api, "inject", lambda sid, role, content: injected.append((sid, role, content))
    )
    monkeypatch.setattr(api, "im_deliver", lambda sid, content: delivered.append((sid, content)))
    store.upsert_meta("im-1", origin="im")
    token, _ = _session_for("admin")
    assert client.post("/admin/sessions/im-1/takeover", headers=_hdr(token)).status_code == 200
    assert store.is_taken_over("im-1") is True
    client.post("/admin/sessions/im-1/inject", headers=_hdr(token), json={"content": "human here"})
    assert injected == [("im-1", "human_agent", "human here")]
    assert delivered == [("im-1", "human here")]  # IM delivered back to platform
    client.post("/admin/sessions/im-1/release", headers=_hdr(token))
    assert store.is_taken_over("im-1") is False


def test_force_end_requires_confirm(client):  # 场景 101 (force end)
    token, _ = _session_for("admin")
    store.upsert_meta("s1", origin="web")
    assert client.post("/admin/sessions/s1/force-end", headers=_hdr(token)).status_code == 428
    r = client.post("/admin/sessions/s1/force-end", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert store.get_meta("s1")["status"] == "ended"


def test_clear_session_confirm_and_delegates(client, monkeypatch):  # 场景 101 (clear)
    cleared = []
    monkeypatch.setattr(api, "clear_session", lambda sid: cleared.append(sid))
    token, _ = _session_for("admin")
    assert client.post("/admin/sessions/s1/clear", headers=_hdr(token)).status_code == 428
    r = client.post("/admin/sessions/s1/clear", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert cleared == ["s1"]


def test_bulk_dispose(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/sessions/bulk",
        headers=_hdr(token, confirm=True),
        json={"session_ids": ["a", "b"], "action": "end"},
    )
    assert r.status_code == 200
    assert r.json()["count"] == 2
    assert store.get_meta("a")["status"] == "ended"


def test_session_detail_replays_meta_and_transcript(client, monkeypatch):  # 场景 100 (回放)
    monkeypatch.setattr(api, "load_transcript", lambda sid: [{"role": "user", "content": "q"}])
    ops = agent_store.get_by_name("ops")
    assert ops is not None
    store.upsert_meta("web-9", origin="web", agent_id=ops.id)
    token, _ = _session_for("admin")
    r = client.get("/admin/sessions/web-9", headers=_hdr(token))
    assert r.status_code == 200
    assert r.json()["meta"]["agent_name"] == "ops"
    assert r.json()["transcript"][0]["content"] == "q"


def test_reset_requires_confirm_and_delegates(client, monkeypatch):  # 场景 101 (重置)
    reset_calls = []
    monkeypatch.setattr(api, "reset_session", lambda sid, keep: reset_calls.append((sid, keep)))
    token, _ = _session_for("admin")
    assert (
        client.post(
            "/admin/sessions/s1/reset", headers=_hdr(token), json={"keep_turns": 2}
        ).status_code
        == 428
    )
    r = client.post(
        "/admin/sessions/s1/reset", headers=_hdr(token, confirm=True), json={"keep_turns": 2}
    )
    assert r.status_code == 200
    assert reset_calls == [("s1", 2)]


def test_viewer_read_only(client):  # 场景 102
    token, _ = _session_for("viewer")
    assert client.get("/admin/sessions", headers=_hdr(token)).status_code == 200
    assert client.post("/admin/sessions/s1/takeover", headers=_hdr(token)).status_code == 403


def test_list_sessions_enriched_with_stats(client, monkeypatch):  # 场景 100 (列表富化)
    ops = agent_store.get_by_name("ops")
    assert ops is not None
    store.upsert_meta("web-1", origin="web", agent_id=ops.id, user_id="u1")
    monkeypatch.setattr(
        api,
        "session_stats",
        lambda sid: {"total_tokens": 42, "rounds": 3, "pending_approvals": 1},
    )
    token, _ = _session_for("admin")
    rows = client.get("/admin/sessions", headers=_hdr(token)).json()
    row = next(r for r in rows if r["session_id"] == "web-1")
    assert row["total_tokens"] == 42
    assert row["rounds"] == 3
    assert row["pending_approvals"] == 1
