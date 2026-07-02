"""Integration: managed webhook source admin REST API (live-webhooks).

Admin-only CRUD over ``/admin/webhooks/sources``. Creating with a secret stores ciphertext and
never echoes the plaintext back. Non-admin sessions are rejected.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    apply_migrations(db_path)
    from cryptography.fernet import Fernet

    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode())
    from fleetent.platform.webhook_management import webhook_admin_api as api

    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True), db_path


def _session_for(role: str) -> str:
    u, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id)


def _hdr(token: str) -> dict:
    return {"Authorization": f"Session {token}"}


def test_no_auth_401(client):
    c, _ = client
    assert c.get("/admin/webhooks/sources").status_code == 401


def test_non_admin_forbidden(client):
    c, _ = client
    token = _session_for("viewer")
    assert (
        c.post(
            "/admin/webhooks/sources", json={"id": "x", "user_id": "u1"}, headers=_hdr(token)
        ).status_code
        == 403
    )


def test_create_list_delete(client):
    c, db_path = client
    from fleetent import agent_store

    agent = agent_store.create_agent("bot", "You are a bot.", [])
    token = _session_for("admin")
    r = c.post(
        "/admin/webhooks/sources",
        json={
            "id": "github-ci",
            "user_id": "u1",
            "agent_id": agent.id,
            "message_template": "pushed {ref}",
            "reply_target": "u-internal-9",
            "secret": "s3cr3t",
        },
        headers=_hdr(token),
    )
    assert r.status_code in (200, 201)
    # response must not echo the plaintext secret
    assert "s3cr3t" not in r.text

    listed = c.get("/admin/webhooks/sources", headers=_hdr(token))
    assert listed.status_code == 200
    ids = {s["id"] for s in listed.json()}
    assert "github-ci" in ids
    assert "s3cr3t" not in listed.text  # never echoed

    # secret is ciphertext in the DB
    conn = sqlite3.connect(db_path)
    raw = conn.execute(
        "SELECT secret_ciphertext FROM webhook_sources WHERE id='github-ci'"
    ).fetchone()[0]
    conn.close()
    assert raw is not None and "s3cr3t" not in raw

    d = c.delete("/admin/webhooks/sources/github-ci", headers=_hdr(token))
    assert d.status_code in (200, 204)
    again = c.get("/admin/webhooks/sources", headers=_hdr(token))
    assert "github-ci" not in {s["id"] for s in again.json()}


def _create_source(c, token, **overrides):
    body = {"id": "s1", "user_id": "u1", "agent_id": None, "secret": "orig"}
    body.update(overrides)
    r = c.post("/admin/webhooks/sources", json=body, headers=_hdr(token))
    assert r.status_code in (200, 201)
    return r


def test_update_regular_fields_default_keeps_secret(client):
    c, _ = client
    token = _session_for("admin")
    _create_source(c, token, message_template="old", enabled=True)

    # secret_action omitted → defaults to keep
    r = c.put(
        "/admin/webhooks/sources/s1",
        json={
            "user_id": "u2",
            "agent_id": None,
            "message_template": "new {ref}",
            "reply_target": "u-9",
            "enabled": False,
        },
        headers=_hdr(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert "orig" not in r.text  # secret never echoed
    assert body["user_id"] == "u2"
    assert body["message_template"] == "new {ref}"
    assert body["reply_target"] == "u-9"
    assert body["enabled"] is False
    assert body["has_secret"] is True  # keep preserved it

    # audit written
    from fleetent import audit_log

    assert audit_log.search_audit(action="webhook.update", target_id="s1")


def test_update_secret_set_then_clear(client):
    c, db_path = client
    token = _session_for("admin")
    _create_source(c, token)

    # set: rotate secret
    r = c.put(
        "/admin/webhooks/sources/s1",
        json={"user_id": "u1", "agent_id": None, "secret_action": "set", "secret": "rotated"},
        headers=_hdr(token),
    )
    assert r.status_code == 200
    assert r.json()["has_secret"] is True
    assert "rotated" not in r.text
    conn = sqlite3.connect(db_path)
    raw = conn.execute("SELECT secret_ciphertext FROM webhook_sources WHERE id='s1'").fetchone()[0]
    conn.close()
    assert raw is not None and "rotated" not in raw

    # clear: drop secret
    r = c.put(
        "/admin/webhooks/sources/s1",
        json={"user_id": "u1", "agent_id": None, "secret_action": "clear"},
        headers=_hdr(token),
    )
    assert r.status_code == 200
    assert r.json()["has_secret"] is False


def test_update_set_without_secret_400(client):
    c, _ = client
    token = _session_for("admin")
    _create_source(c, token)
    r = c.put(
        "/admin/webhooks/sources/s1",
        json={"user_id": "u1", "agent_id": None, "secret_action": "set"},
        headers=_hdr(token),
    )
    assert r.status_code == 400


def test_update_unknown_id_404(client):
    c, _ = client
    token = _session_for("admin")
    r = c.put(
        "/admin/webhooks/sources/ghost",
        json={"user_id": "u1", "agent_id": None},
        headers=_hdr(token),
    )
    assert r.status_code == 404


def test_update_requires_admin(client):
    c, _ = client
    admin = _session_for("admin")
    _create_source(c, admin)
    # no auth
    assert (
        c.put("/admin/webhooks/sources/s1", json={"user_id": "u1", "agent_id": None}).status_code
        == 401
    )
    # non-admin
    viewer = _session_for("viewer")
    assert (
        c.put(
            "/admin/webhooks/sources/s1",
            json={"user_id": "u1", "agent_id": None},
            headers=_hdr(viewer),
        ).status_code
        == 403
    )
