"""Owner-level Slack removed; per-agent Slack started from the index at lifespan."""

import asyncio
from pathlib import Path

import yaml
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import fleetent.im_gateway.slack as slack
import fleetent.server as srv
import fleetent.user_store as us
from fleetent.platform.im_gateway_management import im_connector_config


def _migrate(db_path):
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


def test_slack_removed_from_owner_connector_manager():
    assert "slack" not in srv._connector_manager._factories
    assert "telegram" in srv._connector_manager._factories


def test_slack_removed_from_owner_connector_config_schema():
    assert "slack" not in im_connector_config.PLATFORM_CONFIG_KEYS
    assert "telegram" in im_connector_config.PLATFORM_CONFIG_KEYS


def test_lifespan_starts_per_agent_slack_from_index(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    _migrate(db_path)
    monkeypatch.setattr(us, "DB_PATH", db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    agents = tmp_path / "agents"
    d = agents / "support"
    d.mkdir(parents=True)
    (d / "agent.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "support",
                "version": 1,
                "connectors": {"slack": {"bot_token_env": "SUP_BOT", "app_token_env": "SUP_APP"}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(agents))
    monkeypatch.setenv("SUP_BOT", "xoxb-1")
    monkeypatch.setenv("SUP_APP", "xapp-1")

    async def fake_run(agent_name, owner_id, config):
        await asyncio.Event().wait()  # stay connected

    monkeypatch.setattr(slack, "run", fake_run)

    with TestClient(srv.app):
        assert "support" in srv._slack_supervisor.running()
