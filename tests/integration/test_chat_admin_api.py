"""Tests for chat_admin_api (/admin/chat, /admin/sessions). Covers scenarios 97-102.

agent-runtime / session / im-gateway seams are monkeypatched so the tests exercise
the management behaviour (isolation, overrides, bypass, takeover, guards, audit).
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
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
    monkeypatch.setattr(api, "load_transcript", lambda sid: [])
    monkeypatch.setattr(api, "clear_session", lambda sid: None)
    monkeypatch.setattr(api, "inject", lambda sid, role, content: None)
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str, confirm: bool = False) -> dict:
    h = {"Authorization": f"Session {token}"}
    if confirm:
        h["X-Confirm"] = "true"
    return h


# --- playground isolation (场景 97) ------------------------------------------


def test_playground_start_isolated(client):
    token, _ = _session_for("admin")
    r = client.post("/admin/chat/start", headers=_hdr(token), json={"agent_name": "ops"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert r.json()["origin"] == "playground"
    # not listed among real sessions
    real = client.get("/admin/sessions", headers=_hdr(token)).json()
    assert sid not in {m["session_id"] for m in real}


def test_playground_message_passes_overrides(client, monkeypatch):  # 场景 98
    seen = {}
    monkeypatch.setattr(
        api,
        "run_playground",
        lambda agent, sid, msg, overrides, bypass: (
            seen.update(agent=agent, overrides=overrides, bypass=bypass)
            or {"reply": "ok", "events": []}
        ),
    )
    token, _ = _session_for("admin")
    sid = client.post("/admin/chat/start", headers=_hdr(token), json={"agent_name": "ops"}).json()[
        "session_id"
    ]
    r = client.post(
        f"/admin/chat/{sid}/message",
        headers=_hdr(token),
        json={"message": "hi", "overrides": {"model": "gpt-5.5", "temperature": 0.1}},
    )
    assert r.status_code == 200
    assert seen["overrides"] == {"model": "gpt-5.5", "temperature": 0.1}
    assert seen["agent"] == "ops"


def test_overrides_are_request_scoped(client, monkeypatch):  # 场景 98 (覆盖仅作用本请求)
    seen = []
    monkeypatch.setattr(
        api,
        "run_playground",
        lambda agent, sid, msg, overrides, bypass: (
            seen.append((sid, overrides)) or {"reply": "", "events": []}
        ),
    )
    token, _ = _session_for("admin")
    a = client.post("/admin/chat/start", headers=_hdr(token), json={"agent_name": "ops"}).json()[
        "session_id"
    ]
    b = client.post("/admin/chat/start", headers=_hdr(token), json={"agent_name": "ops"}).json()[
        "session_id"
    ]
    client.post(
        f"/admin/chat/{a}/message",
        headers=_hdr(token),
        json={"message": "hi", "overrides": {"model": "x"}},
    )
    client.post(f"/admin/chat/{b}/message", headers=_hdr(token), json={"message": "hi"})
    by_sid = dict(seen)
    assert by_sid[a] == {"model": "x"}
    assert by_sid[b] is None  # other session unaffected by A's override
    # agent definition metadata is untouched by request-level overrides
    assert store.get_meta(a)["agent_name"] == "ops"


def test_playground_message_rejects_non_playground(client, monkeypatch):
    monkeypatch.setattr(api, "run_playground", lambda *a: {"reply": "", "events": []})
    store.upsert_meta("real-1", origin="web")
    token, _ = _session_for("admin")
    # a non-playground (or non-owned) session is not reachable via the chat endpoint
    r = client.post("/admin/chat/real-1/message", headers=_hdr(token), json={"message": "hi"})
    assert r.status_code == 404


def test_playground_bypass_audited(client, monkeypatch):  # 场景 99
    monkeypatch.setattr(
        api,
        "run_playground",
        lambda agent, sid, msg, overrides, bypass: {"reply": "", "events": [], "bypass": bypass},
    )
    token, _ = _session_for("admin")
    sid = client.post("/admin/chat/start", headers=_hdr(token), json={"agent_name": "ops"}).json()[
        "session_id"
    ]
    client.post(
        f"/admin/chat/{sid}/message",
        headers=_hdr(token),
        json={"message": "hi", "auto_approve_medium": True},
    )
    assert any(a["action"] == "playground_bypass_medium" for a in audit.search_audit())


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
    store.upsert_meta("web-9", origin="web", agent_name="ops")
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
    assert (
        client.post(
            "/admin/chat/start", headers=_hdr(token), json={"agent_name": "ops"}
        ).status_code
        == 403
    )
    assert client.post("/admin/sessions/s1/takeover", headers=_hdr(token)).status_code == 403


def test_export_audited(client):
    token, _ = _session_for("admin")
    sid = client.post("/admin/chat/start", headers=_hdr(token), json={"agent_name": "ops"}).json()[
        "session_id"
    ]
    r = client.get(f"/admin/chat/{sid}/export", headers=_hdr(token))
    assert r.status_code == 200
    assert any(a["action"] == "session_export" for a in audit.search_audit())


def test_export_markdown_format(client, monkeypatch):  # 场景 101 (Markdown 导出)
    monkeypatch.setattr(api, "load_transcript", lambda sid: [{"role": "user", "content": "hi"}])
    token, _ = _session_for("admin")
    sid = client.post("/admin/chat/start", headers=_hdr(token), json={"agent_name": "ops"}).json()[
        "session_id"
    ]
    r = client.get(f"/admin/chat/{sid}/export?fmt=markdown", headers=_hdr(token))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert f"# Session {sid}" in r.text
    assert any(a["action"] == "session_export" for a in audit.search_audit())


def test_purge_expired_playground_removes_unpinned(client, monkeypatch):  # 场景 101 (保留期)
    import datetime as dt

    cleared = []
    monkeypatch.setattr(api, "clear_session", lambda sid: cleared.append(sid))
    store.upsert_meta("pg-old", origin="playground")
    store.upsert_meta("pg-keep", origin="playground")
    store.set_pinned("pg-keep", True)
    future = dt.datetime.now(dt.UTC) + dt.timedelta(days=10)
    out = api.purge_expired_playground(now=future, retention_days=7)
    assert "pg-old" in out["purged"]
    assert "pg-keep" not in out["purged"]
    assert cleared == ["pg-old"]
    # meta removed -> get_meta falls back to default (updated_at None)
    assert store.get_meta("pg-old")["updated_at"] is None


def test_list_sessions_enriched_with_stats(client, monkeypatch):  # 场景 100 (列表富化)
    store.upsert_meta("web-1", origin="web", agent_name="ops", user_id="u1")
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


def test_playground_stream_sse(client, monkeypatch):  # 场景 98 (SSE 流式)
    events = [{"type": "token", "data": "he"}, {"type": "token", "data": "llo"}, {"type": "done"}]
    monkeypatch.setattr(
        api,
        "run_playground_stream",
        lambda agent, sid, msg, overrides, bypass: iter(events),
    )
    token, _ = _session_for("admin")
    sid = client.post("/admin/chat/start", headers=_hdr(token), json={"agent_name": "ops"}).json()[
        "session_id"
    ]
    r = client.post(f"/admin/chat/{sid}/stream", headers=_hdr(token), json={"message": "hi"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "data:" in r.text
    assert "llo" in r.text


# --- per-user chat session history (chat-session-history) ---------------------


def test_chat_start_records_owner(client):
    token, uid = _session_for("admin")
    sid = client.post("/admin/chat/start", headers=_hdr(token), json={"agent_name": "ops"}).json()[
        "session_id"
    ]
    assert store.get_meta(sid)["user_id"] == uid


def test_chat_sessions_listed_per_user(client):
    ta, ua = _session_for("admin")
    tb, ub = _session_for("admin")
    sa = client.post("/admin/chat/start", headers=_hdr(ta), json={"agent_name": "ops"}).json()[
        "session_id"
    ]
    sb = client.post("/admin/chat/start", headers=_hdr(tb), json={"agent_name": "qa"}).json()[
        "session_id"
    ]
    mine_a = {s["session_id"] for s in client.get("/admin/chat/sessions", headers=_hdr(ta)).json()}
    mine_b = {s["session_id"] for s in client.get("/admin/chat/sessions", headers=_hdr(tb)).json()}
    assert sa in mine_a and sb not in mine_a
    assert sb in mine_b and sa not in mine_b


def test_chat_cross_user_access_denied(client, monkeypatch):
    monkeypatch.setattr(api, "run_playground", lambda *a: {"reply": "", "events": []})
    ta, _ = _session_for("admin")
    tb, _ = _session_for("admin")
    sa = client.post("/admin/chat/start", headers=_hdr(ta), json={"agent_name": "ops"}).json()[
        "session_id"
    ]
    # another operator cannot message or export someone else's playground session
    assert (
        client.post(
            f"/admin/chat/{sa}/message", headers=_hdr(tb), json={"message": "hi"}
        ).status_code
        == 404
    )
    assert client.get(f"/admin/chat/{sa}/export", headers=_hdr(tb)).status_code == 404
    # owner still can
    assert (
        client.post(
            f"/admin/chat/{sa}/message", headers=_hdr(ta), json={"message": "hi"}
        ).status_code
        == 200
    )


def test_chat_delete_own_session(client):
    ta, _ = _session_for("admin")
    tb, _ = _session_for("admin")
    sa = client.post("/admin/chat/start", headers=_hdr(ta), json={"agent_name": "ops"}).json()[
        "session_id"
    ]
    # non-owner cannot delete
    assert client.delete(f"/admin/chat/{sa}", headers=_hdr(tb)).status_code == 404
    # owner deletes -> gone from their list
    assert client.delete(f"/admin/chat/{sa}", headers=_hdr(ta)).status_code in (200, 204)
    mine = {s["session_id"] for s in client.get("/admin/chat/sessions", headers=_hdr(ta)).json()}
    assert sa not in mine
