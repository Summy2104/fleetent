"""Owner-level Slack removed; per-agent Slack started from the index at lifespan."""

import fleetent.server as srv
from fleetent.platform.im_gateway_management import im_connector_config
from tests.integration._migration_template import apply_migrations


def _migrate(db_path):
    apply_migrations(db_path)


def test_per_agent_platforms_removed_from_owner_connector_manager():
    # Slack and Telegram are per-agent (supervised from the agent index), not owner-level.
    assert "slack" not in srv._connector_manager._factories
    assert "telegram" not in srv._connector_manager._factories


def test_per_agent_platforms_removed_from_owner_connector_config_schema():
    assert "slack" not in im_connector_config.PLATFORM_CONFIG_KEYS
    assert "telegram" not in im_connector_config.PLATFORM_CONFIG_KEYS
    assert "whatsapp" in im_connector_config.PLATFORM_CONFIG_KEYS
