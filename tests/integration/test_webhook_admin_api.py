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
