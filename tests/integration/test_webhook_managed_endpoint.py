"""Integration: managed platform POST /webhook/{source_id} (live-webhooks).

The public platform edge looks up the source in the management DB, gates (enabled / body size),
verifies HMAC against the decrypted secret, then forwards to the target agent through the node
channel (mocked here). The forward must carry the resolved user_id / message / agent. The forward
runs in the background after an immediate 202.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.integration._migration_template import apply_migrations


def _sig(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    apply_migrations(db_path)
    from cryptography.fernet import Fernet

    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode())

    from fleetent.platform.webhook_management import webhook_inbound_api as api

    forwarded: list = []

    async def _fake_forward(*, agent_name, source_id, body, source_meta):
        forwarded.append(
            {
                "agent_name": agent_name,
                "source_id": source_id,
                "body": body,
                "source_meta": json.loads(source_meta),
            }
        )

    monkeypatch.setattr(api, "_forward", _fake_forward)
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app, raise_server_exceptions=True)
    return client, forwarded


def test_unknown_source_404(setup):
    client, forwarded = setup
    assert client.post("/webhook/nope", json={"x": 1}).status_code == 404
    assert forwarded == []


def test_disabled_source_403(setup):
    client, forwarded = setup
    from fleetent.platform.webhook_management import webhook_source_store as store

    # 403 happens before agent resolution, so agent_id may be unset (NULL) here.
    store.put_source(id="gh", user_id="u1", agent_id=None, enabled=False)
    assert client.post("/webhook/gh", json={"x": 1}).status_code == 403
    assert forwarded == []


def test_hmac_failure_403(setup):
    client, forwarded = setup
    from fleetent.platform.webhook_management import webhook_source_store as store

    store.put_source(id="gh", user_id="u1", agent_id=None, secret="s3cr3t")
    resp = client.post(
        "/webhook/gh",
        content=json.dumps({"x": 1}),
        headers={"X-Hub-Signature-256": "sha256=bad", "Content-Type": "application/json"},
    )
    assert resp.status_code == 403
    assert forwarded == []


def test_success_202_and_forwards_with_resolved_fields(setup):
    client, forwarded = setup
    from fleetent import agent_store
    from fleetent.platform.webhook_management import webhook_source_store as store

    agent = agent_store.create_agent("bot", "You are a bot.", [])
    store.put_source(
        id="gh",
        user_id="u-managed",
        agent_id=agent.id,
        message_template="pushed {ref}",
        reply_target="u-internal-9",
        secret="s3cr3t",
    )
    body = json.dumps({"ref": "main"}).encode()
    resp = client.post(
        "/webhook/gh",
        content=body,
        headers={
            "X-Hub-Signature-256": _sig("s3cr3t", body),
            "Content-Type": "application/json",
        },
    )
    assert resp.status_code == 202
    assert len(forwarded) == 1
    fwd = forwarded[0]
    assert fwd["agent_name"] == "bot"  # resolved from agent_id
    assert fwd["source_id"] == "gh"
    assert fwd["source_meta"]["user_id"] == "u-managed"
    assert fwd["source_meta"]["agent_name"] == "bot"
    assert fwd["source_meta"]["reply_target"] == "u-internal-9"
    assert fwd["source_meta"]["message_template"] == "pushed {ref}"
    assert fwd["body"] == body


def test_no_target_agent_409(setup):
    client, forwarded = setup
    from fleetent.platform.webhook_management import webhook_source_store as store

    store.put_source(id="gh", user_id="u1", agent_id=None)  # no target agent
    assert client.post("/webhook/gh", json={"x": 1}).status_code == 409
    assert forwarded == []


def test_no_secret_source_accepts_without_signature(setup):
    client, forwarded = setup
    from fleetent import agent_store
    from fleetent.platform.webhook_management import webhook_source_store as store

    agent = agent_store.create_agent("bot", "You are a bot.", [])
    store.put_source(id="open", user_id="u1", agent_id=agent.id)
    resp = client.post("/webhook/open", json={"ref": "main"})
    assert resp.status_code == 202
    assert len(forwarded) == 1
