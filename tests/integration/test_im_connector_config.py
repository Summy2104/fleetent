import json
from types import SimpleNamespace

import pytest

import fleetent.platform.im_gateway_management.connector_config as icc
import fleetent.platform.im_gateway_management.connector_store as ics
import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
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
    # Slack and Telegram are per-agent now; owner-level .env fallback covers WhatsApp.
    _env(monkeypatch, whatsapp_access_token="wa-env")
    assert icc.resolve(_owner(), "whatsapp") == {"access_token": "wa-env"}


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
    _env(monkeypatch, whatsapp_access_token="wa-e")  # slack/telegram are per-agent, not seeded
    seeded = icc.seed_from_env()
    assert "whatsapp" in seeded
    assert (
        "slack" not in seeded and "telegram" not in seeded
    )  # owner-level per-agent platforms removed
    whatsapp = ics.get_connector(_owner(), "whatsapp")
    assert json.loads(whatsapp["config"]) == {"access_token": "wa-e"}
    assert whatsapp["enabled"] == 1


def test_platform_config_keys_schema():
    keys = icc.PLATFORM_CONFIG_KEYS
    assert "slack" not in keys  # per-agent (per-agent-slack-connector), not owner-level
    assert "telegram" not in keys  # per-agent (per-agent-telegram-connector), not owner-level
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
    _env(monkeypatch, whatsapp_access_token="wa-e")
    icc.seed_from_env()
    # change env, seed again without force -> whatsapp config unchanged
    _env(monkeypatch, whatsapp_access_token="wa-CHANGED")
    icc.seed_from_env()
    assert json.loads(ics.get_connector(_owner(), "whatsapp")["config"])["access_token"] == "wa-e"
    # with force -> overwritten
    icc.seed_from_env(force=True)
    assert (
        json.loads(ics.get_connector(_owner(), "whatsapp")["config"])["access_token"]
        == "wa-CHANGED"
    )
