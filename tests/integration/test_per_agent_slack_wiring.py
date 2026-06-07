"""Owner-level Slack removed; per-agent Slack started from the index at lifespan."""

from pathlib import Path

from alembic import command
from alembic.config import Config

import fleetent.server as srv
from fleetent.platform.im_gateway_management import im_connector_config


def _migrate(db_path):
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def test_per_agent_platforms_removed_from_owner_connector_manager():
    # Slack and Telegram are per-agent (supervised from the agent index), not owner-level.
    assert "slack" not in srv._connector_manager._factories
    assert "telegram" not in srv._connector_manager._factories


def test_per_agent_platforms_removed_from_owner_connector_config_schema():
    assert "slack" not in im_connector_config.PLATFORM_CONFIG_KEYS
    assert "telegram" not in im_connector_config.PLATFORM_CONFIG_KEYS
    assert "whatsapp" in im_connector_config.PLATFORM_CONFIG_KEYS
