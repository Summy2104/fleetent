"""Integration tests for DB-authored agent definitions materialized to agent.yaml."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import fleetent.agent_store as agent_store
from fleetent.agent_config import default_models
from fleetent.platform.agent_lifecycle import materialize
from fleetent.platform.connector_management import agent_mcp_server_store
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.model_provider_management import provider_admin_store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_agent_file_from_store_exports_authored_runtime_config(db):
    provider_admin_store.add_provider(
        "claude-fast",
        "https://api.anthropic.com/v1/",
        "claude-haiku-4-5-20251001",
        provider="anthropic",
        protocol="openai_chat",
        api_key_env="FLEETENT_AGENT_SUPPORT_CLAUDE_FAST",
        max_tokens=2048,
        params={"temperature": 0.2},
    )
    provider_admin_store.add_provider(
        "embed",
        "https://api.openai.com/v1/embeddings",
        "text-embedding-3-small",
        provider="openai",
        protocol="http_embedding",
        api_key_env="FLEETENT_AGENT_SUPPORT_OPENAI",
        params={"dimensions": 1536},
    )
    agent = agent_store.create_agent(
        "support",
        "You are support.",
        ["search_*", "docs__*"],
        skills_dir="agents/support/skills",
        mcp_server_ids=["docs"],
        model_overrides={
            "default": [{"provider_id": "claude-fast"}],
            "embedding": [{"provider_id": "embed", "params": {"dimensions": 768}}],
        },
        memory_namespace="support-memory",
        tenant_id="acme",
        team_id="support",
    )
    agent_mcp_server_store.add_mcp_server(
        None,
        "docs",
        transport="http",
        url="https://docs.acme.internal/mcp",
        auth_type="bearer",
        api_key_env="FLEETENT_AGENT_SUPPORT_DOCS",
    )
    agent_store.bind_mcp_server(agent.id, "docs")
    agent_store.assign_user("u_alice", agent.id)
    agent_store.assign_channel("slack", "C0123", agent.id)
    agent_kbs_store.bind("acme", "support-kb", str(agent.id), created_by="admin")

    exported = materialize.agent_file_from_store(agent_store.get_by_name("support"))

    assert exported.tenant_id == "acme"
    assert exported.team_id == "support"
    assert exported.skills_dir == "agents/support/skills"
    assert exported.memory_namespace == "support-memory"
    assert exported.mcp_servers[0].id == "docs"
    assert exported.mcp_servers[0].api_key_env == "FLEETENT_AGENT_SUPPORT_DOCS"
    assert exported.bindings.users == ["u_alice"]
    assert exported.bindings.channels == ["slack:C0123"]
    assert exported.knowledge.enabled is True
    assert exported.knowledge.bindings[0].tenant_id == "acme"
    assert exported.knowledge.bindings[0].kb_id == "support-kb"
    assert exported.knowledge.bindings[0].default is True

    targets = {target.id: target for target in exported.models.targets}
    assert set(targets) == {"claude-fast", "embed"}
    assert targets["claude-fast"].provider == "anthropic"
    assert targets["claude-fast"].protocol == "openai_chat"
    assert targets["claude-fast"].base_url == "https://api.anthropic.com/v1/"
    assert targets["claude-fast"].model == "claude-haiku-4-5-20251001"
    assert targets["claude-fast"].api_key_env == "FLEETENT_AGENT_SUPPORT_CLAUDE_FAST"
    assert targets["claude-fast"].max_tokens == 2048
    assert targets["claude-fast"].params == {"temperature": 0.2}
    assert targets["embed"].endpoint == "https://api.openai.com/v1/embeddings"
    assert targets["embed"].api_key_env == "FLEETENT_AGENT_SUPPORT_OPENAI"
    assert targets["embed"].params == {"dimensions": 1536}
    assert exported.models.routes["default"][0].target == "claude-fast"
    assert exported.models.routes["embedding"][0].target == "embed"
    assert exported.models.routes["embedding"][0].params == {"dimensions": 768}
    assert not any(
        (target.base_url or "").startswith("http://localhost")
        or (target.endpoint or "").startswith("http://localhost")
        for target in exported.models.targets
    )


def test_agent_file_from_store_defaults_models_when_no_overrides(db):
    agent = agent_store.create_agent("basic", "p", [])

    exported = materialize.agent_file_from_store(agent)

    assert exported.models == default_models()
