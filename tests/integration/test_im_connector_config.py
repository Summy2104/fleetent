import json
from types import SimpleNamespace

import pytest

import fleetent.platform.im_gateway_management.im_connector_config as icc
import fleetent.platform.im_gateway_management.im_connector_store as ics
import fleetent.user_store as user_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(user_store, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(ics, "DB_PATH", tmp_path / "users.db")
    ics._init_db()
    return tmp_path / "users.db"


def _owner():
    return user_store.admin_owner_id()


def _env(monkeypatch, **kw):
    defaults = {"slack_bot_token": "", "slack_app_token": "", "telegram_bot_token": ""}
    defaults.update(kw)
    monkeypatch.setattr(icc, "get_settings", lambda: SimpleNamespace(**defaults))


def test_resolve_prefers_db_config(db, monkeypatch):
    _env(monkeypatch, slack_bot_token="xoxb-from-env")
    ics.upsert_connector(
        _owner(), "slack", config=json.dumps({"bot_token": "xoxb-db", "app_token": "xapp-db"})
    )
    assert icc.resolve(_owner(), "slack") == {"bot_token": "xoxb-db", "app_token": "xapp-db"}


def test_resolve_falls_back_to_env(db, monkeypatch):
    # Slack is per-agent now; owner-level .env fallback covers Telegram.
    _env(monkeypatch, telegram_bot_token="tg-env")
    assert icc.resolve(_owner(), "telegram") == {"bot_token": "tg-env"}


def test_resolve_masked_exposes_only_last4(db, monkeypatch):
    _env(monkeypatch)
    ics.upsert_connector(_owner(), "slack", config=json.dumps({"bot_token": "xoxb-1234567890abcd"}))
    masked = icc.resolve_masked(_owner(), "slack")["bot_token"]
    assert masked.endswith("abcd")
    assert "1234567890" not in masked


def test_set_config_writes_db(db, monkeypatch):
    _env(monkeypatch)
    icc.set_config(_owner(), "telegram", {"bot_token": "123:newtoken"})
    assert icc.resolve(_owner(), "telegram") == {"bot_token": "123:newtoken"}


def test_seed_from_env_populates_and_enables(db, monkeypatch):
    _env(monkeypatch, telegram_bot_token="tg-e")  # slack is per-agent, not seeded
    seeded = icc.seed_from_env()
    assert "telegram" in seeded
    assert "slack" not in seeded  # owner-level Slack removed
    telegram = ics.get_connector(_owner(), "telegram")
    assert json.loads(telegram["config"]) == {"bot_token": "tg-e"}
    assert telegram["enabled"] == 1


def test_platform_config_keys_schema():
    keys = icc.PLATFORM_CONFIG_KEYS
    assert keys["telegram"] == ["bot_token"]
    assert "slack" not in keys  # per-agent (per-agent-slack-connector), not owner-level
    assert keys["whatsapp"] == [
        "phone_number_id",
        "access_token",
        "verify_token",
        "business_account_id",
    ]


def test_resolve_masked_masks_whatsapp_access_token(db, monkeypatch):
    _env(monkeypatch)
    icc.set_config(_owner(), "whatsapp", {"access_token": "EAAG1234567890wxyz"})
    masked = icc.resolve_masked(_owner(), "whatsapp")["access_token"]
    assert masked.endswith("wxyz")
    assert "1234567890" not in masked


def test_seed_is_idempotent_unless_force(db, monkeypatch):
    _env(monkeypatch, telegram_bot_token="tg-e")
    icc.seed_from_env()
    # change env, seed again without force -> telegram config unchanged
    _env(monkeypatch, telegram_bot_token="tg-CHANGED")
    icc.seed_from_env()
    assert json.loads(ics.get_connector(_owner(), "telegram")["config"])["bot_token"] == "tg-e"
    # with force -> overwritten
    icc.seed_from_env(force=True)
    assert (
        json.loads(ics.get_connector(_owner(), "telegram")["config"])["bot_token"] == "tg-CHANGED"
    )
