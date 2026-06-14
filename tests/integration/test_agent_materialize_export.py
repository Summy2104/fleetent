"""Integration tests for DB-authored agent definitions materialized to agent.yaml."""

import pytest

import fleetent.agent_store as agent_store
from fleetent.agent_config import default_models
from fleetent.platform.agent_lifecycle import materialize
from fleetent.platform.agent_management_console import agent_im_group_store
from fleetent.platform.connector_management import agent_mcp_server_store
from fleetent.platform.knowledge_base_management import agent_kbs_store
from fleetent.platform.model_provider_management import provider_admin_store
from fleetent.platform.tenancy import store as tenancy_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def test_agent_file_from_store_exports_authored_runtime_config(db):
    tenancy_store.create_tenant(id="acme", name="Acme")
    tenancy_store.create_team(id="support", tenant_id="acme", name="Support")
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
    agent_kbs_store.bind("acme", "support-kb", agent.id, created_by="admin")

    exported = materialize.agent_file_from_store(agent_store.get_by_name("support"))

    assert exported.tenant_id == "acme"
    assert exported.team_id == "support"
    assert exported.skills_dir == "agents/support/skills"
    assert exported.memory_namespace == "support-memory"
    assert exported.mcp_servers[0].id == "docs"
    assert exported.mcp_servers[0].api_key_env == "FLEETENT_AGENT_SUPPORT_DOCS"
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


def test_agent_file_from_store_applies_config_overrides(db):
    """The per-agent config_overrides blob deep-merges onto the materialized agent.yaml."""
    agent = agent_store.create_agent(
        "ov",
        "p",
        [],
        # top-level `access` moved into per-connector declarations; exercise the
        # deep-merge with a current scalar + nested block instead.
        config_overrides={
            "agent_max_turns": 80,
            "knowledge": {"retrieval_policy": {"top_k": 7}},
        },
    )

    af = materialize.agent_file_from_store(agent)

    assert af.agent_max_turns == 80
    assert af.knowledge.retrieval_policy.top_k == 7
    assert af.knowledge.retrieval_policy.mode == "hybrid"  # untouched nested default
    assert af.knowledge.enabled is False  # untouched sibling default preserved


def test_agent_file_from_store_materializes_im_access_without_clobbering_credentials(db):
    agent = agent_store.create_agent(
        "support",
        "p",
        [],
        config_overrides={
            "connectors": {
                "slack": {
                    "bot_token_env": "SUPPORT_SLACK_BOT",
                    "app_token_env": "SUPPORT_SLACK_APP",
                }
            }
        },
    )
    agent_store.assign_user("u_alice", agent.id)
    agent_store.assign_user("u_bob", agent.id)
    agent_store.set_im_capabilities("support", supports_dm=True, supports_groups=True)
    agent_im_group_store.bind(agent.id, "slack", "C_ops", created_by="admin")
    agent_im_group_store.bind(agent.id, "slack", "C_eng", created_by="admin")

    exported = materialize.agent_file_from_store(agent_store.get_by_name("support"))

    assert exported.connectors.supports_dm is True
    assert exported.connectors.supports_groups is True
    assert exported.connectors.slack is not None
    assert exported.connectors.slack.bot_token_env == "SUPPORT_SLACK_BOT"
    assert exported.connectors.slack.app_token_env == "SUPPORT_SLACK_APP"
    assert exported.connectors.slack.access.allow_users == ["u_alice", "u_bob"]
    assert exported.connectors.slack.access.allow_channels == ["C_eng", "C_ops"]
    assert exported.connectors.slack.access.require_approval is True


def test_agent_file_from_store_ignores_invalid_config_override(db):
    agent = agent_store.create_agent("ov2", "p", [], config_overrides={"not_a_real_field": 1})
    # a bad override must not break materialize — fall back to the valid base
    assert materialize.agent_file_from_store(agent).name == "ov2"


def test_seed_env_falls_back_to_provider_inline_key(db, tmp_path, monkeypatch):
    """A provider authored with an inline key seeds the agent .env for its derived env name."""
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    provider_admin_store.add_provider(
        "inline-prov",
        "https://api.anthropic.com/v1/",
        "claude-opus-4-8",
        provider="anthropic",
        protocol="openai_chat",
        api_key="sk-inline-secret",
        api_key_env="FLEETENT_MODEL_INLINE_PROV_API_KEY",
    )
    agent = agent_store.create_agent(
        "seeded",
        "p",
        [],
        model_overrides={"default": {"provider": "inline-prov", "model": "claude-opus-4-8"}},
    )
    home = materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)
    env_text = (home / ".env").read_text(encoding="utf-8")
    assert "FLEETENT_MODEL_INLINE_PROV_API_KEY=sk-inline-secret" in env_text


def test_agent_file_from_store_exports_active_version(db):
    agent_store.create_agent("ver", "v1", [])
    assert materialize.agent_file_from_store(agent_store.get_by_name("ver")).version == 1
    agent_store.create_version("ver", system_prompt="v2")  # active becomes v2
    assert materialize.agent_file_from_store(agent_store.get_by_name("ver")).version == 2


def test_agent_file_from_store_handles_targets_routes_shape(db):
    """Agents authored with the {targets, routes:{name:[{target}]}} shape still materialize.

    Pre-existing agents store this shape; the expander must resolve each route entry's
    ``target`` against the provider registry (not choke on the wrapper keys).
    """
    provider_admin_store.add_provider(
        "p-router",
        "https://api.anthropic.com/v1/",
        "claude-opus-4-8",
        provider="anthropic",
        protocol="openai_chat",
        api_key_env="FLEETENT_P_ROUTER",
    )
    agent = agent_store.create_agent(
        "routed",
        "p",
        [],
        model_overrides={
            "targets": ["p-router"],
            "routes": {"reasoning": [{"target": "p-router", "max_tokens": None, "params": {}}]},
        },
    )

    exported = materialize.agent_file_from_store(agent)

    assert exported.models.routes["reasoning"][0].target == "p-router"
    target = {t.id: t for t in exported.models.targets}["p-router"]
    assert target.base_url == "https://api.anthropic.com/v1/"
    assert target.model == "claude-opus-4-8"


def test_agent_file_from_store_handles_ui_provider_key(db):
    """The console emits {route: {provider: <id>, model}}; resolve <id> against providers."""
    provider_admin_store.add_provider(
        "p-ui",
        "https://api.openai.com/v1/",
        "gpt-5.5",
        provider="openai",
        protocol="openai_chat",
        api_key_env="FLEETENT_P_UI",
    )
    agent = agent_store.create_agent(
        "uimodel", "p", [], model_overrides={"default": {"provider": "p-ui", "model": "gpt-5.5"}}
    )

    exported = materialize.agent_file_from_store(agent)

    target = {t.id: t for t in exported.models.targets}["p-ui"]
    assert target.base_url == "https://api.openai.com/v1/"
    assert exported.models.routes["default"][0].target == "p-ui"


# ── skill DB state → agent.yaml (skill-materialize-db-fields) ──────────────────


def test_materialize_writes_global_disabled_skills(db):
    """A globally-disabled skill lands in AgentFile.disabled_skills."""
    from fleetent.platform.skill_management import skill_admin_store

    agent = agent_store.create_agent("support", "p", [])
    skill_admin_store.set_global_enabled("crm-ops", False)
    skill_admin_store.set_global_enabled("jira", True)

    exported = materialize.agent_file_from_store(agent)

    assert "crm-ops" in exported.disabled_skills
    assert "jira" not in exported.disabled_skills


def test_materialize_disabled_skills_safe_when_no_states(db):
    """No skill_admin_state rows → disabled_skills is empty, no error."""
    agent = agent_store.create_agent("support", "p", [])

    exported = materialize.agent_file_from_store(agent)

    assert exported.disabled_skills == []


def test_materialize_allowed_skills_from_binding(db):
    """With bindings, allowed_skills is exactly the enabled=1 subset."""
    from fleetent.platform.skill_management import skill_admin_store

    agent = agent_store.create_agent("support", "p", [], allowed_skills=["authored"])
    skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by=None)
    skill_admin_store.set_binding(agent.id, "billing", False, updated_by=None)

    exported = materialize.agent_file_from_store(agent)

    assert exported.allowed_skills == ["crm-ops"]


def test_materialize_allowed_skills_empty_when_all_bindings_disabled(db):
    """All bindings disabled → allowed_skills empty (narrowed to none), no fallback."""
    from fleetent.platform.skill_management import skill_admin_store

    agent = agent_store.create_agent("support", "p", [], allowed_skills=["authored"])
    skill_admin_store.set_binding(agent.id, "crm-ops", False, updated_by=None)

    exported = materialize.agent_file_from_store(agent)

    assert exported.allowed_skills == []


def test_materialize_allowed_skills_falls_back_to_authored_when_no_binding(db):
    """No agent_skills rows → fall back to authored allowed_skills."""
    agent = agent_store.create_agent("support", "p", [], allowed_skills=["jira"])

    exported = materialize.agent_file_from_store(agent)

    assert exported.allowed_skills == ["jira"]


# ── skill files copied into agent home (skill-files-per-agent-home) ───────────


def test_write_home_copies_skill_files_into_home(db, tmp_path, monkeypatch):
    """write_home() copies the global skills dir into <home>/skills/."""
    skills_src = tmp_path / "global_skills"
    (skills_src / "crm-ops").mkdir(parents=True)
    (skills_src / "crm-ops" / "SKILL.md").write_text(
        "---\nname: crm-ops\ndescription: CRM ops\n---\nbody", encoding="utf-8"
    )
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(skills_src))

    agent = agent_store.create_agent("support", "p", [])
    home = materialize.write_home(materialize.agent_file_from_store(agent))

    copied = home / "skills" / "crm-ops" / "SKILL.md"
    assert copied.is_file()
    assert "CRM ops" in copied.read_text(encoding="utf-8")


def test_write_home_safe_when_skills_dir_missing(db, tmp_path, monkeypatch):
    """No global skills dir → write_home() still succeeds, no error."""
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(tmp_path / "does_not_exist"))

    agent = agent_store.create_agent("support", "p", [])
    home = materialize.write_home(materialize.agent_file_from_store(agent))

    assert (home / "agent.yaml").is_file()  # home written despite no skills


def test_write_home_skill_copy_is_idempotent(db, tmp_path, monkeypatch):
    """Running write_home() twice does not error on the existing skills dir."""
    skills_src = tmp_path / "global_skills"
    (skills_src / "crm-ops").mkdir(parents=True)
    (skills_src / "crm-ops" / "SKILL.md").write_text(
        "---\nname: crm-ops\ndescription: CRM ops\n---\nbody", encoding="utf-8"
    )
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(skills_src))

    agent = agent_store.create_agent("support", "p", [])
    materialize.write_home(materialize.agent_file_from_store(agent))
    home = materialize.write_home(materialize.agent_file_from_store(agent))

    assert (home / "skills" / "crm-ops" / "SKILL.md").is_file()


# ── list_all_names + rematerialize_all (skill-admin-trigger-rematerialize) ────


def test_list_all_names_returns_sorted_agent_names(db):
    """agent_store.list_all_names() returns every authored agent, sorted."""
    agent_store.create_agent("zeta", "p", [])
    agent_store.create_agent("alpha", "p", [])
    agent_store.create_agent("mid", "p", [])

    assert agent_store.list_all_names() == ["alpha", "mid", "zeta"]


def test_list_all_names_empty_when_no_agents(db):
    """No authored agents → empty list, no error."""
    assert agent_store.list_all_names() == []


def test_rematerialize_all_writes_every_agent_home(db):
    """rematerialize_all() exports a home for each agent and returns their names."""
    agent_store.create_agent("alpha", "p", [])
    agent_store.create_agent("beta", "p", [])

    done = materialize.rematerialize_all()

    assert set(done) == {"alpha", "beta"}
    assert (materialize.home_dir("alpha") / "agent.yaml").is_file()
    assert (materialize.home_dir("beta") / "agent.yaml").is_file()


def test_rematerialize_all_empty_when_no_agents(db):
    """No agents → empty result, no error."""
    assert materialize.rematerialize_all() == []
