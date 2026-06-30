"""Integration: managed webhook source storage (live-webhooks).

Schema by Alembic against a tmp_path management DB (DATABASE_URL env). The HMAC secret is
stored as Fernet ciphertext (never plaintext in the table). put/get/list/delete by id. No
raw sqlite3 / ORM in the store — all SQL goes through the unified ``fleetent.db`` boundary.
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from cryptography.fernet import Fernet

    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode())
    return db_path


def test_migration_creates_webhook_sources_table(db):
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "webhook_sources" in tables


def test_put_get_roundtrip_and_secret_is_ciphertext(db):
    from fleetent.platform.webhook_management import webhook_source_store as store

    from fleetent import agent_store

    agent = agent_store.create_agent("bot", "You are a bot.", [])
    store.put_source(
        id="github-ci",
        agent_id=agent.id,
        user_id="u1",
        message_template="pushed {ref}",
        reply_target="u-internal-9",
        enabled=True,
        secret="s3cr3t",
    )
    src = store.get_source("github-ci")
    assert src is not None
    assert src.agent_id == agent.id
    assert src.user_id == "u1"
    assert src.message_template == "pushed {ref}"
    assert src.reply_target == "u-internal-9"
    assert src.enabled is True
    assert src.secret == "s3cr3t"  # decrypted on read

    # plaintext secret must NOT be present in the stored row
    conn = sqlite3.connect(db)
    raw = conn.execute(
        "SELECT secret_ciphertext FROM webhook_sources WHERE id='github-ci'"
    ).fetchone()[0]
    conn.close()
    assert raw is not None
    assert "s3cr3t" not in raw


def test_get_unknown_returns_none(db):
    from fleetent.platform.webhook_management import webhook_source_store as store

    assert store.get_source("nope") is None


def test_list_and_delete(db):
    from fleetent.platform.webhook_management import webhook_source_store as store

    store.put_source(id="a", agent_id=None, user_id="u1")
    store.put_source(id="b", agent_id=None, user_id="u2")
    ids = {s.id for s in store.list_sources()}
    assert ids == {"a", "b"}
    store.delete_source("a")
    assert {s.id for s in store.list_sources()} == {"b"}


def test_put_without_secret_stores_null(db):
    from fleetent.platform.webhook_management import webhook_source_store as store

    store.put_source(id="nosec", agent_id=None, user_id="u1")
    src = store.get_source("nosec")
    assert src is not None
    assert src.secret is None
