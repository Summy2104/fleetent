"""DB→file export: agent_file_from_store materializes the full authored definition.

Covers the gap where model/mcp/bindings/knowledge/tenant/team/skills_dir were dropped
and models fell back to the localhost placeholder regardless of authored providers.
"""

from pathlib import Path

import pytest

import fleetent.agent_store as agent_store
import fleetent.user_store as us
from fleetent.platform.agent_lifecycle import materialize
from fleetent.platform.connector_management import agent_mcp_server_store
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.model_provider_management import provider_admin_store


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
    _migrate(db_path)
    return tmp_path


def test_exports_tenant_team_skills_dir(db):
    agent = agent_store.create_agent(
        "support", "Help.", ["shell"], skills_dir="skills", tenant_id="acme", team_id="cs"
    )
    af = materialize.agent_file_from_store(agent)
    assert af.tenant_id == "acme"
    assert af.team_id == "cs"
    assert af.skills_dir == "skills"


def test_model_overrides_expand_to_real_targets_reusing_provider_key(db):
    provider_admin_store.add_provider(
        "anthropic-primary",
        base_url="https://api.anthropic.com/v1/",
        model="claude-opus-4-8",
        provider="anthropic",
        protocol="openai_chat",
        api_key_env="FLEETENT_MODEL_PRIMARY_API_KEY",
        max_tokens=4096,
    )
    agent = agent_store.create_agent(
        "support",
        "Help.",
        ["shell"],
        model_overrides={"default": {"provider": "anthropic-primary", "model": "claude-opus-4-8"}},
    )
    af = materialize.agent_file_from_store(agent)

    target = next(t for t in af.models.targets if t.api_key_env == "FLEETENT_MODEL_PRIMARY_API_KEY")
    assert target.base_url == "https://api.anthropic.com/v1/"
    assert target.model == "claude-opus-4-8"
    assert all("localhost" not in (t.base_url or "") for t in af.models.targets)
    assert af.models.routes["default"][0].target == target.id


def test_targets_routes_shape_expands(db):
    for pid, model in (("p-fast", "claude-haiku"), ("p-smart", "claude-opus")):
        provider_admin_store.add_provider(
            pid,
            base_url="https://api.anthropic.com/v1/",
            model=model,
            provider="anthropic",
            protocol="openai_chat",
            api_key_env=f"{pid.upper().replace('-', '_')}_KEY",
        )
    agent = agent_store.create_agent(
        "support",
        "Help.",
        ["shell"],
        model_overrides={
            "targets": ["p-fast", "p-smart"],
            "routes": {"default": "p-smart", "fast": "p-fast"},
        },
    )
    af = materialize.agent_file_from_store(agent)
    assert {t.id for t in af.models.targets} == {"p-fast", "p-smart"}
    assert af.models.routes["default"][0].target == "p-smart"
    assert af.models.routes["fast"][0].target == "p-fast"


def test_targets_without_routes_get_default_route(db):
    provider_admin_store.add_provider(
        "only", base_url="https://x/v1/", model="m", provider="anthropic", protocol="openai_chat"
    )
    agent = agent_store.create_agent(
        "support", "Help.", ["shell"], model_overrides={"targets": ["only"], "routes": {}}
    )
    af = materialize.agent_file_from_store(agent)
    assert af.models.routes["default"][0].target == "only"


def test_no_model_overrides_falls_back_to_default_models(db):
    agent = agent_store.create_agent("bare", "Help.", ["shell"])
    af = materialize.agent_file_from_store(agent)
    assert {t.id for t in af.models.targets} == {t.id for t in materialize.default_models().targets}


def test_exports_mcp_servers_bindings_and_knowledge(db):
    agent_mcp_server_store.add_mcp_server(
        None,
        "docs",
        transport="http",
        url="https://docs.acme.internal/mcp",
        auth_type="bearer",
        api_key_env="ACME_DOCS_MCP_TOKEN",
    )
    agent = agent_store.create_agent("support", "Help.", ["shell"], tenant_id="acme")
    agent_store.bind_mcp_server(agent.id, "docs")
    agent_store.assign_user("u_alice", agent.id)
    agent_store.assign_channel("slack", "C123", agent.id)
    agent_kbs_store.bind("acme", "support-kb", str(agent.id))

    af = materialize.agent_file_from_store(agent)

    assert [s.id for s in af.mcp_servers] == ["docs"]
    assert af.mcp_servers[0].api_key_env == "ACME_DOCS_MCP_TOKEN"
    assert af.bindings.users == ["u_alice"]
    assert af.bindings.channels == ["slack:C123"]
    assert af.knowledge.enabled is True
    assert [(b.tenant_id, b.kb_id) for b in af.knowledge.bindings] == [("acme", "support-kb")]
