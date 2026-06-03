"""Owner-scoped connector credential resolution; env fallback admin-owner only."""

import datetime
import sqlite3
import types

import pytest

from fleetent import user_store
from fleetent.platform.im_gateway_management import im_connector_config as cfg
from fleetent.platform.im_gateway_management import im_connector_store as store


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "users.db"
    monkeypatch.setattr(user_store, "DB_PATH", p)
    monkeypatch.setattr(store, "DB_PATH", p)
    now = datetime.datetime.now(datetime.UTC).isoformat()
    user_store._init_db()
    with sqlite3.connect(str(p)) as c:
        c.execute(
            "INSERT INTO users (id, name, api_key, created_at, role)"
            " VALUES ('admin1', 'admin', 'ma-x', ?, 'built_in_admin')",
            (now,),
        )
    fake = types.SimpleNamespace(telegram_bot_token="env-tg", slack_bot_token="")
    monkeypatch.setattr(cfg, "get_settings", lambda: fake)
    return p


def test_admin_owner_inherits_env(db):
    assert cfg.resolve("admin1", "telegram") == {"bot_token": "env-tg"}


def test_non_admin_owner_no_env(db):
    assert cfg.resolve("ownerB", "telegram") == {}


def test_db_config_overrides_env(db):
    cfg.set_config("ownerB", "telegram", {"bot_token": "db-tg"})
    assert cfg.resolve("ownerB", "telegram") == {"bot_token": "db-tg"}
    assert cfg.resolve("admin1", "telegram") == {"bot_token": "env-tg"}


def test_masked(db):
    cfg.set_config("ownerB", "telegram", {"bot_token": "abcd1234"})
    assert cfg.resolve_masked("ownerB", "telegram") == {"bot_token": "****1234"}


def test_seed_from_env_targets_admin_owner(db):
    seeded = cfg.seed_from_env()
    assert "telegram" in seeded
    assert store.get_connector("admin1", "telegram") is not None
    # nothing seeded under a non-admin owner
    assert store.list_connectors("ownerB") == []
