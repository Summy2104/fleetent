"""materialize resolves inject-mode secrets into .env; operator slots stay blank."""

from pathlib import Path

import pytest
import yaml
from cryptography.fernet import Fernet

import fleetent.agent_store as agent_store
import fleetent.user_store as us
from fleetent.platform.agent_lifecycle import materialize
from fleetent.platform.connector_management import agent_mcp_server_store
from fleetent.platform.model_provider_management import provider_admin_store
from fleetent.platform.secret_management import agent_secret_store


def _migrate(db_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    db_path = tmp_path / "users.db"
    monkeypatch.setattr(us, "DB_PATH", db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode())
    _migrate(db_path)
    return tmp_path


def _agent_with_model_and_mcp():
    provider_admin_store.add_provider(
        "anthropic-primary",
        base_url="https://api.anthropic.com/v1/",
        model="claude-opus-4-8",
        provider="anthropic",
        protocol="openai_chat",
        api_key_env="FLEETENT_MODEL_PRIMARY_API_KEY",
    )
    agent_mcp_server_store.add_mcp_server(
        None, "docs", transport="http", url="https://x/mcp", api_key_env="ACME_DOCS_MCP_TOKEN"
    )
    agent = agent_store.create_agent(
        "support",
        "Help.",
        ["shell"],
        model_overrides={"default": {"provider": "anthropic-primary", "model": "claude-opus-4-8"}},
    )
    agent_store.bind_mcp_server(agent.id, "docs")
    return agent


def test_inject_slot_written_operator_slot_blank(db):
    agent = _agent_with_model_and_mcp()
    agent_secret_store.set_secret(agent.id, "ACME_DOCS_MCP_TOKEN", "mcp-real-token")

    home = materialize.materialize_from_store("support")
    env_text = (home / ".env").read_text(encoding="utf-8")

    assert "ACME_DOCS_MCP_TOKEN=mcp-real-token" in env_text  # inject value resolved
    assert "FLEETENT_MODEL_PRIMARY_API_KEY=" in env_text  # operator slot present, blank
    # operator slot has no value
    for line in env_text.splitlines():
        if line.startswith("FLEETENT_MODEL_PRIMARY_API_KEY="):
            assert line.split("=", 1)[1] == ""


def test_operator_value_preserved_across_rematerialize(db):
    _agent_with_model_and_mcp()
    materialize.materialize_from_store("support")
    home = materialize.home_dir("support")
    # operator fills the model key on the host
    (home / ".env").write_text("FLEETENT_MODEL_PRIMARY_API_KEY=sk-operator\n", encoding="utf-8")

    materialize.materialize_from_store("support")
    env_text = (home / ".env").read_text(encoding="utf-8")
    assert "FLEETENT_MODEL_PRIMARY_API_KEY=sk-operator" in env_text


def test_agent_yaml_never_contains_secret_value(db):
    agent = _agent_with_model_and_mcp()
    agent_secret_store.set_secret(agent.id, "ACME_DOCS_MCP_TOKEN", "mcp-real-token")
    home = materialize.materialize_from_store("support")
    yaml_text = (home / "agent.yaml").read_text(encoding="utf-8")
    assert "mcp-real-token" not in yaml_text
    data = yaml.safe_load(yaml_text)
    assert "mode" not in data


def test_inject_set_but_decrypt_fails_is_loud(db, monkeypatch):
    agent = _agent_with_model_and_mcp()
    agent_secret_store.set_secret(agent.id, "ACME_DOCS_MCP_TOKEN", "mcp-real-token")
    # rotate the master key so the stored ciphertext can no longer be decrypted
    monkeypatch.setenv("FLEETENT_SECRET_KEY", Fernet.generate_key().decode())
    with pytest.raises(agent_secret_store.SecretKeyError):
        materialize.materialize_from_store("support")
