import json
from types import SimpleNamespace

import pytest

import fleetent.im_connector_config as icc
import fleetent.im_connector_store as ics
import fleetent.user_store as user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(ics, "DB_PATH", tmp_path / "users.db")
    ics._init_db()
    return tmp_path / "users.db"


def _env(monkeypatch, **kw):
    defaults = {"slack_bot_token": "", "slack_app_token": "", "telegram_bot_token": ""}
    defaults.update(kw)
    monkeypatch.setattr(icc, "get_settings", lambda: SimpleNamespace(**defaults))


def test_resolve_prefers_db_config(db, monkeypatch):
    _env(monkeypatch, slack_bot_token="xoxb-from-env")
    ics.upsert_connector(
        "slack", config=json.dumps({"bot_token": "xoxb-db", "app_token": "xapp-db"})
    )
    assert icc.resolve("slack") == {"bot_token": "xoxb-db", "app_token": "xapp-db"}


def test_resolve_falls_back_to_env(db, monkeypatch):
    _env(monkeypatch, slack_bot_token="xoxb-env", slack_app_token="xapp-env")
    assert icc.resolve("slack") == {"bot_token": "xoxb-env", "app_token": "xapp-env"}


def test_resolve_masked_exposes_only_last4(db, monkeypatch):
    _env(monkeypatch)
    ics.upsert_connector("slack", config=json.dumps({"bot_token": "xoxb-1234567890abcd"}))
    masked = icc.resolve_masked("slack")["bot_token"]
    assert masked.endswith("abcd")
    assert "1234567890" not in masked


def test_set_config_writes_db(db, monkeypatch):
    _env(monkeypatch)
    icc.set_config("telegram", {"bot_token": "123:newtoken"})
    assert icc.resolve("telegram") == {"bot_token": "123:newtoken"}


def test_seed_from_env_populates_and_enables(db, monkeypatch):
    _env(monkeypatch, slack_bot_token="xoxb-e", slack_app_token="xapp-e")  # telegram empty
    seeded = icc.seed_from_env()
    assert "slack" in seeded
    slack = ics.get_connector("slack")
    assert json.loads(slack["config"]) == {"bot_token": "xoxb-e", "app_token": "xapp-e"}
    assert slack["enabled"] == 1
    telegram = ics.get_connector("telegram")
    assert telegram["status"] == "unconfigured"
    assert telegram["enabled"] == 0


def test_seed_is_idempotent_unless_force(db, monkeypatch):
    _env(monkeypatch, slack_bot_token="xoxb-e", slack_app_token="xapp-e")
    icc.seed_from_env()
    # change env, seed again without force -> slack config unchanged
    _env(monkeypatch, slack_bot_token="xoxb-CHANGED", slack_app_token="xapp-e")
    icc.seed_from_env()
    assert json.loads(ics.get_connector("slack")["config"])["bot_token"] == "xoxb-e"
    # with force -> overwritten
    icc.seed_from_env(force=True)
    assert json.loads(ics.get_connector("slack")["config"])["bot_token"] == "xoxb-CHANGED"
