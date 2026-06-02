"""Tests for chat_admin_api (/admin/chat, /admin/sessions). Covers scenarios 97-102.

agent-runtime / session / im-gateway seams are monkeypatched so the tests exercise
the management behaviour (isolation, overrides, bypass, takeover, guards, audit).
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.chat_admin_api as api
import fleetent.governance.audit_log as audit
import fleetent.session_admin_store as store
import fleetent.user_store as user_store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    for mod in (user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    user_store._init_db()
    audit._init_db()
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


def test_playground_message_rejects_non_playground(client, monkeypatch):
    monkeypatch.setattr(api, "run_playground", lambda *a: {"reply": "", "events": []})
    store.upsert_meta("real-1", origin="web")
    token, _ = _session_for("admin")
    r = client.post("/admin/chat/real-1/message", headers=_hdr(token), json={"message": "hi"})
    assert r.status_code == 409


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
    r = client.get("/admin/chat/s1/export", headers=_hdr(token))
    assert r.status_code == 200
    assert any(a["action"] == "session_export" for a in audit.search_audit())
