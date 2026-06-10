"""Owner-scoped connector credential resolution; env fallback admin-owner only."""

import datetime
import sqlite3
import types

import pytest

from fleetent import user_store
from fleetent.platform.im_gateway_management import connector_config as cfg
from fleetent.platform.im_gateway_management import connector_store as store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "users.db"
    monkeypatch.setattr(user_store, "DB_PATH", p)
    monkeypatch.setattr(store, "DB_PATH", p)
    apply_migrations(p)
    now = datetime.datetime.now(datetime.UTC).isoformat()
    user_store._init_db()
    with sqlite3.connect(str(p)) as c:
        c.execute(
            "INSERT INTO users (id, name, api_key, created_at, role)"
            " VALUES ('admin1', 'admin', 'ma-x', ?, 'built_in_admin')",
            (now,),
        )
    # Slack and Telegram are per-agent now; WhatsApp is the owner-level platform.
    fake = types.SimpleNamespace(whatsapp_access_token="env-wa")
    monkeypatch.setattr(cfg, "get_settings", lambda: fake)
    return p


def test_admin_owner_inherits_env(db):
    assert cfg.resolve("admin1", "whatsapp") == {"access_token": "env-wa"}


def test_non_admin_owner_no_env(db):
    assert cfg.resolve("ownerB", "whatsapp") == {}


def test_db_config_overrides_env(db):
    cfg.set_config("ownerB", "whatsapp", {"access_token": "db-wa"})
    assert cfg.resolve("ownerB", "whatsapp") == {"access_token": "db-wa"}
    assert cfg.resolve("admin1", "whatsapp") == {"access_token": "env-wa"}


def test_masked(db):
    cfg.set_config("ownerB", "whatsapp", {"access_token": "abcd1234"})
    assert cfg.resolve_masked("ownerB", "whatsapp") == {"access_token": "****1234"}


def test_seed_from_env_targets_admin_owner(db):
    seeded = cfg.seed_from_env()
    assert "whatsapp" in seeded
    assert store.get_connector("admin1", "whatsapp") is not None
    # nothing seeded under a non-admin owner
    assert store.list_connectors("ownerB") == []
