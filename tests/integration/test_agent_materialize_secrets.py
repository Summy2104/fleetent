"""Integration tests for materialize .env secret resolution."""

import base64
import re

import pytest

import fleetent.agent_store as agent_store
from fleetent.platform.agent_lifecycle import credential_slots, materialize, secret_store
from fleetent.platform.model_provider_management import provider_admin_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"2" * 32).decode("ascii"),
    )
    return db_path


def _agent_with_model_env(env_name: str = "FLEETENT_AGENT_SUPPORT_MODEL") -> agent_store.Agent:
    provider_admin_store.add_provider(
        "claude-fast",
        "https://api.anthropic.com/v1/",
        "claude-haiku-4-5-20251001",
        provider="anthropic",
        protocol="openai_chat",
        api_key_env=env_name,
    )
    return agent_store.create_agent(
        "support",
        "p",
        [],
        model_overrides={"default": [{"provider_id": "claude-fast"}]},
    )


def test_materialize_injects_decrypted_secret_and_keeps_yaml_secret_free(db, tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    agent = _agent_with_model_env()
    credential_slots.ensure_slot(
        agent,
        "env:FLEETENT_AGENT_SUPPORT_MODEL",
        mode="inject",
        env_name="FLEETENT_AGENT_SUPPORT_MODEL",
    )
    secret_store.set(agent.id, "FLEETENT_AGENT_SUPPORT_MODEL", "sk-live-secret", "admin")

    home = materialize.write_home(
        materialize.agent_file_from_store(agent_store.get_by_name("support")),
        source_agent=agent,
    )

    assert "FLEETENT_AGENT_SUPPORT_MODEL=sk-live-secret" in (home / ".env").read_text(
        encoding="utf-8"
    )
    assert "sk-live-secret" not in (home / "agent.yaml").read_text(encoding="utf-8")


def test_materialize_operator_preserves_existing_value_or_writes_empty(db, tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    agent = _agent_with_model_env()
    credential_slots.ensure_slot(
        agent,
        "env:FLEETENT_AGENT_SUPPORT_MODEL",
        mode="operator",
        env_name="FLEETENT_AGENT_SUPPORT_MODEL",
    )
    home = tmp_path / "tenants" / "default" / "agents" / "support"
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_AGENT_SUPPORT_MODEL=operator-secret\n", encoding="utf-8")

    materialize.write_home(
        materialize.agent_file_from_store(agent_store.get_by_name("support")),
        source_agent=agent,
    )

    assert "FLEETENT_AGENT_SUPPORT_MODEL=operator-secret" in (home / ".env").read_text(
        encoding="utf-8"
    )

    (home / ".env").unlink()
    materialize.write_home(
        materialize.agent_file_from_store(agent_store.get_by_name("support")),
        source_agent=agent,
    )
    env_text = (home / ".env").read_text(encoding="utf-8")
    assert "FLEETENT_AGENT_SUPPORT_MODEL=\n" in env_text
    assert re.search(r"^FLEETENT_TUI_TOKEN=ma-[0-9a-f]{64}$", env_text, re.MULTILINE) is not None


def test_materialize_inject_set_with_bad_key_fails_loud(db, tmp_path, monkeypatch):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    agent = _agent_with_model_env()
    credential_slots.ensure_slot(
        agent,
        "env:FLEETENT_AGENT_SUPPORT_MODEL",
        mode="inject",
        env_name="FLEETENT_AGENT_SUPPORT_MODEL",
    )
    secret_store.set(agent.id, "FLEETENT_AGENT_SUPPORT_MODEL", "sk-live-secret", "admin")
    monkeypatch.setenv(
        "FLEETENT_SECRET_KEY",
        base64.urlsafe_b64encode(b"3" * 32).decode("ascii"),
    )

    with pytest.raises(secret_store.SecretKeyError, match="FLEETENT_SECRET_KEY"):
        materialize.write_home(
            materialize.agent_file_from_store(agent_store.get_by_name("support")),
            source_agent=agent,
        )


def test_materialize_seeds_managed_tui_token_without_leaking_desired_state(
    db, tmp_path, monkeypatch
):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    agent = _agent_with_model_env()

    home = tmp_path / "tenants" / "default" / "agents" / "support"
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-existing-token\n", encoding="utf-8")

    materialize.write_home(
        materialize.agent_file_from_store(agent_store.get_by_name("support")),
        source_agent=agent,
    )

    assert "FLEETENT_TUI_TOKEN=ma-existing-token" in (home / ".env").read_text(encoding="utf-8")
    assert secret_store.get_decrypted(agent.id, "FLEETENT_TUI_TOKEN") == "ma-existing-token"

    (home / ".env").write_text("", encoding="utf-8")
    secret_store.delete(agent.id, "FLEETENT_TUI_TOKEN")

    materialize.write_home(
        materialize.agent_file_from_store(agent_store.get_by_name("support")),
        source_agent=agent,
    )

    env_text = (home / ".env").read_text(encoding="utf-8")
    match = re.search(r"^FLEETENT_TUI_TOKEN=(ma-[0-9a-f]{64})$", env_text, re.MULTILINE)
    assert match is not None
    assert secret_store.get_decrypted(agent.id, "FLEETENT_TUI_TOKEN") == match.group(1)

    payload = materialize.desired_state_payload_from_agent_file(
        materialize.agent_file_from_store(agent_store.get_by_name("support"))
    )
    assert "FLEETENT_TUI_TOKEN" not in str(payload)
    assert match.group(1) not in str(payload)


def test_seed_env_prefers_agent_inject_then_provider_key_then_shared_secret(
    db, tmp_path, monkeypatch
):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    provider_admin_store.add_provider(
        "shared-provider",
        "https://api.openai.com/v1/",
        "gpt-5",
        provider="openai",
        protocol="openai_chat",
        api_key="shared-provider-key",
        api_key_env="FLEETENT_SHARED_MODEL_KEY",
    )
    agent = agent_store.create_agent(
        "support",
        "p",
        [],
        model_overrides={"default": [{"provider_id": "shared-provider"}]},
    )
    home = tmp_path / "tenants" / "default" / "agents" / "support"
    home.mkdir(parents=True)

    secret_store.set(None, "FLEETENT_SHARED_MODEL_KEY", "shared-secret-store", "admin")
    materialize.write_home(
        materialize.agent_file_from_store(agent_store.get_by_name("support")),
        source_agent=agent,
    )
    assert "FLEETENT_SHARED_MODEL_KEY=shared-provider-key" in (home / ".env").read_text(
        encoding="utf-8"
    )

    credential_slots.ensure_slot(
        agent,
        "env:FLEETENT_SHARED_MODEL_KEY",
        mode="inject",
        env_name="FLEETENT_SHARED_MODEL_KEY",
    )
    secret_store.set(agent.id, "FLEETENT_SHARED_MODEL_KEY", "agent-override-key", "admin")
    materialize.write_home(
        materialize.agent_file_from_store(agent_store.get_by_name("support")),
        source_agent=agent,
    )
    assert "FLEETENT_SHARED_MODEL_KEY=agent-override-key" in (home / ".env").read_text(
        encoding="utf-8"
    )

    secret_store.delete(agent.id, "FLEETENT_SHARED_MODEL_KEY")
    provider_admin_store.edit_provider("shared-provider", api_key="")
    materialize.write_home(
        materialize.agent_file_from_store(agent_store.get_by_name("support")),
        source_agent=agent,
    )
    assert "FLEETENT_SHARED_MODEL_KEY=shared-secret-store" in (home / ".env").read_text(
        encoding="utf-8"
    )


def test_rematerialize_all_refreshes_split_registry_agents_without_blank_model_envs(
    db, tmp_path, monkeypatch
):
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    provider_admin_store.add_provider(
        "chat-provider",
        provider="anthropic",
        api_key="provider-inline-key",
        api_key_env="FLEETENT_CHAT_KEY",
    )
    provider_admin_store.add_provider(
        "embed-provider",
        provider="openai",
        api_key_env="FLEETENT_EMBED_KEY",
    )
    from fleetent.platform.model_provider_management import model_admin_store

    model_admin_store.add_model(
        "chat-model",
        provider_id="chat-provider",
        protocol="openai_chat",
        model_name="claude-sonnet",
        base_url="https://chat.example/v1",
    )
    model_admin_store.add_model(
        "embed-model",
        provider_id="embed-provider",
        protocol="http_embedding",
        model_name="text-embedding-3-small",
        endpoint="https://embed.example/v1/embeddings",
    )
    agent_store.create_agent(
        "chat-agent",
        "p",
        [],
        model_overrides={"routes": {"default": [{"model_id": "chat-model"}]}},
    )
    agent_store.create_agent(
        "embed-agent",
        "p",
        [],
        model_overrides={"routes": {"default": [{"model_id": "embed-model"}]}},
    )
    secret_store.set(None, "FLEETENT_EMBED_KEY", "shared-embed-key", "admin")

    done = materialize.rematerialize_all()

    assert set(done) == {"chat-agent", "embed-agent"}
    chat_env = (tmp_path / "tenants" / "default" / "agents" / "chat-agent" / ".env").read_text(
        encoding="utf-8"
    )
    embed_env = (tmp_path / "tenants" / "default" / "agents" / "embed-agent" / ".env").read_text(
        encoding="utf-8"
    )
    assert "FLEETENT_CHAT_KEY=provider-inline-key" in chat_env
    assert "FLEETENT_EMBED_KEY=shared-embed-key" in embed_env
    assert "FLEETENT_CHAT_KEY=\n" not in chat_env
    assert "FLEETENT_EMBED_KEY=\n" not in embed_env
