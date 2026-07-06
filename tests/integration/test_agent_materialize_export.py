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
        auth_type="api_key",
        auth_config={"key_env": "FLEETENT_AGENT_SUPPORT_DOCS"},
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
    # Overriding "default" and "embedding" leaves "memory_extraction"/"kb_extraction" (still
    # pointing at the baseline "default" target) and "vision" (untouched route) alive rather than
    # dropping them — the platform default targets they reference must survive too.
    assert set(targets) == {"claude-fast", "embed", "default", "vision"}
    assert targets["claude-fast"].provider == "anthropic"
    assert targets["claude-fast"].protocol == "openai_chat"
    assert targets["claude-fast"].base_url == "https://api.anthropic.com/v1/"
    assert targets["claude-fast"].model == "claude-haiku-4-5-20251001"
    assert targets["claude-fast"].api_key_env == "FLEETENT_AGENT_SUPPORT_CLAUDE_FAST"
    assert targets["claude-fast"].max_tokens == 2048
    assert targets["claude-fast"].params == {"temperature": 0.2}
    assert targets["embed"].endpoint == "https://api.openai.com/v1/embeddings"
    assert targets["embed"].api_key_env == "FLEETENT_AGENT_SUPPORT_OPENAI"
    assert targets["embed"].params == {"dimensions": 768}
    assert exported.models.routes["default"][0].target == "claude-fast"
    assert exported.models.routes["embedding"][0].target == "embed"
    assert exported.models.routes["embedding"][0].params == {"dimensions": 768}

    baseline = default_models()
    assert exported.models.routes["memory_extraction"] == baseline.routes["memory_extraction"]
    assert exported.models.routes["kb_extraction"] == baseline.routes["kb_extraction"]
    assert exported.models.routes["vision"] == baseline.routes["vision"]
    # The authored targets (claude-fast/embed) must never point at the local dev placeholder;
    # memory_extraction/kb_extraction/vision fall back to it precisely because this agent never
    # authored those routes, which is the documented, intentional default (agent-scoped-model-
    # routing's "Platform materializes model config" merge semantics), not a leak.
    assert not any(
        (targets[target_id].base_url or "").startswith("http://localhost")
        or (targets[target_id].endpoint or "").startswith("http://localhost")
        for target_id in ("claude-fast", "embed")
    )


def test_agent_file_from_store_expands_vision_kb_extraction_rerank_routes(db):
    """Newly UI-exposed routes (vision/kb_extraction/rerank) expand with the right protocol."""
    provider_admin_store.add_provider(
        "chat-model",
        "https://api.anthropic.com/v1/",
        "claude-sonnet-4-5",
        provider="anthropic",
        protocol="openai_chat",
        api_key_env="FLEETENT_AGENT_R_CHAT",
        max_tokens=4096,
    )
    provider_admin_store.add_provider(
        "rerank-model",
        "https://rerank.acme.internal/rerank",
        "bge-reranker-large",
        provider="acme",
        protocol="http_rerank",
        api_key_env="FLEETENT_AGENT_R_RERANK",
    )
    agent_store.create_agent(
        "router",
        "You are router.",
        ["search_*"],
        model_overrides={
            "vision": [{"provider_id": "chat-model"}],
            "kb_extraction": [{"provider_id": "chat-model"}],
            "rerank": [{"provider_id": "rerank-model"}],
        },
    )

    exported = materialize.agent_file_from_store(agent_store.get_by_name("router"))
    targets = {target.id: target for target in exported.models.targets}

    assert exported.models.routes["vision"][0].target == "chat-model"
    assert exported.models.routes["kb_extraction"][0].target == "chat-model"
    assert exported.models.routes["rerank"][0].target == "rerank-model"
    assert targets["chat-model"].protocol == "openai_chat"
    assert targets["rerank-model"].protocol == "http_rerank"
    assert targets["rerank-model"].endpoint == "https://rerank.acme.internal/rerank"


def test_agent_file_from_store_expands_fallback_chain_with_per_entry_params(db):
    """A route authored with 2 entries + per-entry overrides materializes into an ordered
    fallback chain, and resolve() merges each entry's params/max_tokens over its target."""
    from fleetent.model import ModelPolicySnapshot

    provider_admin_store.add_provider(
        "primary-chat",
        "https://api.anthropic.com/v1/",
        "claude-sonnet-4-5",
        provider="anthropic",
        protocol="openai_chat",
        api_key_env="FLEETENT_AGENT_C_PRIMARY",
        max_tokens=4096,
        params={"temperature": 0.2},
    )
    provider_admin_store.add_provider(
        "backup-chat",
        "https://vllm.acme.internal/v1/",
        "qwen3-32b",
        provider="acme",
        protocol="openai_chat",
        api_key_env="FLEETENT_AGENT_C_BACKUP",
        max_tokens=2048,
    )
    agent_store.create_agent(
        "chained",
        "You are chained.",
        ["search_*"],
        model_overrides={
            "default": [
                {"model_id": "primary-chat", "params": {"temperature": 0.7}},
                {"model_id": "backup-chat", "max_tokens": 1024, "params": {"temperature": 0.5}},
            ]
        },
    )

    exported = materialize.agent_file_from_store(agent_store.get_by_name("chained"))
    chain = exported.models.routes["default"]
    assert [entry.target for entry in chain] == ["primary-chat", "backup-chat"]

    resolved = ModelPolicySnapshot.from_agent(exported).resolve("default")
    assert [r.target_id for r in resolved] == ["primary-chat", "backup-chat"]
    # Entry params override the target's registered params; entry max_tokens wins when set.
    assert resolved[0].params["temperature"] == 0.7
    assert resolved[1].params["temperature"] == 0.5
    assert resolved[1].max_tokens == 1024


def test_agent_file_from_store_expands_named_tiers_referenced_by_routes(db):
    """Named tier targets (primary/backup) are built from the `targets` block and routes
    reference them by name, with two-level param merge (tier default + per-route override)."""
    from fleetent.model import ModelPolicySnapshot

    provider_admin_store.add_provider(
        "gpt4o",
        "https://api.openai.example/v1/",
        "gpt-4o",
        provider="openai",
        protocol="openai_chat",
        api_key_env="FLEETENT_AGENT_T_GPT",
        max_tokens=4096,
        params={"temperature": 0.5},
    )
    provider_admin_store.add_provider(
        "qwen",
        "https://vllm.acme.internal/v1/",
        "qwen3-32b",
        provider="acme",
        protocol="openai_chat",
        api_key_env="FLEETENT_AGENT_T_QWEN",
    )
    agent_store.create_agent(
        "tiered",
        "You are tiered.",
        ["search_*"],
        model_overrides={
            "targets": {
                "primary": {"model_id": "gpt4o"},
                "backup": {"model_id": "qwen"},
            },
            "routes": {
                "default": [
                    {"target": "primary", "params": {"temperature": 0.7}},
                    {"target": "backup"},
                ],
                "vision": [{"target": "primary", "params": {"temperature": 0.2}}],
            },
        },
    )

    exported = materialize.agent_file_from_store(agent_store.get_by_name("tiered"))
    targets = {target.id: target for target in exported.models.targets}
    assert "primary" in targets and "backup" in targets
    assert targets["primary"].model == "gpt-4o"
    assert targets["backup"].model == "qwen3-32b"
    assert [entry.target for entry in exported.models.routes["default"]] == ["primary", "backup"]
    assert [entry.target for entry in exported.models.routes["vision"]] == ["primary"]

    policy = ModelPolicySnapshot.from_agent(exported)
    default_chain = policy.resolve("default")
    assert [r.target_id for r in default_chain] == ["primary", "backup"]
    assert default_chain[0].params["temperature"] == 0.7  # route override beats tier default
    # vision reuses the SAME primary tier at a different per-route temperature.
    assert policy.resolve("vision")[0].params["temperature"] == 0.2


def test_named_tier_route_entry_dropped_when_tier_undefined(db):
    """A route entry referencing an undefined tier is dropped rather than materializing a bogus
    target (no `backup` tier defined -> that entry disappears, no phantom target)."""
    provider_admin_store.add_provider(
        "gpt4o",
        "https://api.openai.example/v1/",
        "gpt-4o",
        provider="openai",
        protocol="openai_chat",
        api_key_env="FLEETENT_AGENT_U_GPT",
    )
    agent_store.create_agent(
        "partial",
        "p",
        ["search_*"],
        model_overrides={
            "targets": {"primary": {"model_id": "gpt4o"}},
            "routes": {"default": [{"target": "primary"}, {"target": "backup"}]},
        },
    )

    exported = materialize.agent_file_from_store(agent_store.get_by_name("partial"))
    assert [entry.target for entry in exported.models.routes["default"]] == ["primary"]
    assert "backup" not in {target.id for target in exported.models.targets}


def test_agent_file_from_store_exports_mcp_headers(db):
    """MCP 自定义 headers 必须随 materialize 导出（mcp-headers-managed-sync）。"""
    agent = agent_store.create_agent("support", "p", [], mcp_server_ids=["docs"])
    agent_mcp_server_store.add_mcp_server(
        None,
        "docs",
        transport="http",
        url="https://docs.acme.internal/mcp",
        headers={"X-API-Key": "env:DOCS_KEY"},
    )
    agent_store.bind_mcp_server(agent.id, "docs")

    exported = materialize.agent_file_from_store(agent_store.get_by_name("support"))

    assert exported.mcp_servers[0].headers == {"X-API-Key": "env:DOCS_KEY"}


def test_agent_file_from_store_translates_structured_mcp_auth(db):
    agent = agent_store.create_agent("support", "p", [], mcp_server_ids=["docs", "oauth"])
    agent_mcp_server_store.add_mcp_server(
        None,
        "docs",
        transport="http",
        url="https://docs.acme.internal/mcp",
        auth_type="api_key",
        auth_config={"key_env": "FLEETENT_AGENT_SUPPORT_DOCS"},
    )
    agent_mcp_server_store.add_mcp_server(
        None,
        "oauth",
        transport="http",
        url="https://oauth.acme.internal/mcp",
        auth_type="oauth_client_credentials",
        auth_config={
            "token_url": "https://auth.acme.internal/token",
            "client_id": "support-agent",
            "client_secret_env": "FLEETENT_AGENT_SUPPORT_OAUTH_SECRET",
            "scope": "tools:read",
        },
    )
    agent_store.bind_mcp_server(agent.id, "docs")
    agent_store.bind_mcp_server(agent.id, "oauth")

    exported = materialize.agent_file_from_store(agent_store.get_by_name("support"))
    servers = {server.id: server for server in exported.mcp_servers}

    assert servers["docs"].auth_type == "api_key"
    assert servers["docs"].api_key_env == "FLEETENT_AGENT_SUPPORT_DOCS"
    assert servers["docs"].auth is None
    assert servers["oauth"].auth_type == "oauth_client_credentials"
    assert servers["oauth"].api_key_env == ""
    assert servers["oauth"].auth is not None
    assert servers["oauth"].auth.grant == "client_credentials"
    assert servers["oauth"].auth.token_url == "https://auth.acme.internal/token"
    assert servers["oauth"].auth.client_id == "support-agent"
    assert servers["oauth"].auth.client_secret_env == "FLEETENT_AGENT_SUPPORT_OAUTH_SECRET"
    assert servers["oauth"].auth.scope == "tools:read"


def test_desired_state_payload_includes_mcp_headers(db):
    """headers 不在 secret-strip 名单里，必须出现在发往 node 的 desired-state payload。"""
    agent = agent_store.create_agent("support", "p", [], mcp_server_ids=["docs"])
    agent_mcp_server_store.add_mcp_server(
        None,
        "docs",
        transport="http",
        url="https://docs.acme.internal/mcp",
        headers={"X-API-Key": "env:DOCS_KEY"},
    )
    agent_store.bind_mcp_server(agent.id, "docs")

    payload = materialize.desired_state_payload_from_agent_file(
        materialize.agent_file_from_store(agent_store.get_by_name("support"))
    )

    assert payload["mcpServers"]["docs"]["headers"] == {"X-API-Key": "env:DOCS_KEY"}


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
            "im": {
                "slack": {
                    "bot_token_env": "SUPPORT_SLACK_BOT",
                    "app_token_env": "SUPPORT_SLACK_APP",
                }
            }
        },
    )
    agent_store.assign_user("u_alice", agent.id)
    agent_store.assign_user("u_bob", agent.id)
    agent_store.set_im_capabilities(agent.id, supports_dm=True, supports_groups=True)
    agent_im_group_store.bind(agent.id, "slack", "C_ops", created_by="admin")
    agent_im_group_store.bind(agent.id, "slack", "C_eng", created_by="admin")

    exported = materialize.agent_file_from_store(agent_store.get_by_name("support"))

    assert exported.im.supports_dm is True
    assert exported.im.supports_groups is True
    assert exported.im.slack is not None
    assert exported.im.slack.bot_token_env == "SUPPORT_SLACK_BOT"
    assert exported.im.slack.app_token_env == "SUPPORT_SLACK_APP"
    assert exported.im.slack.access.allow_users == ["u_alice", "u_bob"]
    assert exported.im.slack.access.allow_groups == ["C_eng", "C_ops"]
    assert exported.im.slack.access.require_approval is True


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
    agent_store.update_agent_config("ver", system_prompt="v2")
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


def test_write_home_preserves_drifted_skill_copy_and_logs_skip(db, tmp_path, monkeypatch):
    from fleetent.platform.skill_management import skill_admin_store

    class _Logger:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict[str, object]]] = []

        def debug(self, *_args, **_kwargs) -> None:
            return None

        def warn(self, name: str, **kwargs) -> None:
            self.events.append((name, kwargs))

        def info(self, name: str, **kwargs) -> None:
            self.events.append((name, kwargs))

    skills_src = tmp_path / "global_skills"
    (skills_src / "crm-ops").mkdir(parents=True)
    (skills_src / "crm-ops" / "SKILL.md").write_text(
        "---\nname: crm-ops\ndescription: CRM ops\n---\npool-v1", encoding="utf-8"
    )
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(skills_src))
    logger = _Logger()
    monkeypatch.setattr(materialize, "_logger", logger)

    agent = agent_store.create_agent("support", "p", [])
    skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by=None)

    home = materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)
    evolved = home / "skills" / "crm-ops" / "SKILL.md"
    evolved.write_text(
        "---\n"
        "name: crm-ops\n"
        "description: CRM ops\n"
        "proposal_id: pr-1\n"
        "applied_at: 2026-06-14T00:00:00+00:00\n"
        "---\n"
        "evolved-copy",
        encoding="utf-8",
    )

    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)

    assert "evolved-copy" in evolved.read_text(encoding="utf-8")
    assert skill_admin_store.get_drift(agent.id, "crm-ops")["drift"] == 1
    assert any(event[0] == "agent_home_skill_copy_skipped_drift" for event in logger.events)


def test_write_home_refreshes_non_drifted_skill_and_updates_base_version(db, tmp_path, monkeypatch):
    from fleetent.platform.skill_management import skill_admin_store

    skills_src = tmp_path / "global_skills"
    (skills_src / "billing").mkdir(parents=True)
    skill_file = skills_src / "billing" / "SKILL.md"
    skill_file.write_text(
        "---\nname: billing\ndescription: Billing ops\n---\npool-v1", encoding="utf-8"
    )
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(skills_src))

    agent = agent_store.create_agent("support", "p", [])
    skill_admin_store.set_binding(agent.id, "billing", True, updated_by=None)

    home = materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)
    skill_file.write_text(
        "---\nname: billing\ndescription: Billing ops\n---\npool-v2", encoding="utf-8"
    )

    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)

    copied = home / "skills" / "billing" / "SKILL.md"
    drift = skill_admin_store.get_drift(agent.id, "billing")
    assert "pool-v2" in copied.read_text(encoding="utf-8")
    assert drift["drift"] == 0
    assert drift["base_version"] == materialize._skill_dir_version(skills_src / "billing")


def test_write_home_handles_drift_per_skill_subdirectory(db, tmp_path, monkeypatch):
    from fleetent.platform.skill_management import skill_admin_store

    skills_src = tmp_path / "global_skills"
    for name, body in {"crm-ops": "pool-crm-v1", "billing": "pool-billing-v1"}.items():
        (skills_src / name).mkdir(parents=True)
        (skills_src / name / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {name}\n---\n{body}",
            encoding="utf-8",
        )
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(skills_src))

    agent = agent_store.create_agent("support", "p", [])
    skill_admin_store.set_binding(agent.id, "crm-ops", True, updated_by=None)
    skill_admin_store.set_binding(agent.id, "billing", True, updated_by=None)

    home = materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)
    (home / "skills" / "crm-ops" / "SKILL.md").write_text(
        "---\n"
        "name: crm-ops\n"
        "description: crm-ops\n"
        "proposal_id: pr-1\n"
        "applied_at: 2026-06-14T00:00:00+00:00\n"
        "---\n"
        "evolved-crm",
        encoding="utf-8",
    )
    (skills_src / "billing" / "SKILL.md").write_text(
        "---\nname: billing\ndescription: billing\n---\npool-billing-v2",
        encoding="utf-8",
    )

    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)

    assert "evolved-crm" in (home / "skills" / "crm-ops" / "SKILL.md").read_text(encoding="utf-8")
    assert "pool-billing-v2" in (home / "skills" / "billing" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert skill_admin_store.get_drift(agent.id, "crm-ops")["drift"] == 1
    assert skill_admin_store.get_drift(agent.id, "billing")["drift"] == 0


def test_write_home_marks_drift_from_hash_mismatch_without_runtime_platform_write(
    db, tmp_path, monkeypatch
):
    from fleetent.platform.skill_management import skill_admin_store

    skills_src = tmp_path / "global_skills"
    (skills_src / "search").mkdir(parents=True)
    (skills_src / "search" / "SKILL.md").write_text(
        "---\nname: search\ndescription: Search\n---\npool-v1", encoding="utf-8"
    )
    monkeypatch.setenv("FLEETENT_SKILLS_DIR", str(skills_src))

    agent = agent_store.create_agent("support", "p", [])
    skill_admin_store.set_binding(agent.id, "search", True, updated_by=None)

    home = materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)
    local_copy = home / "skills" / "search" / "SKILL.md"
    local_copy.write_text(
        "---\nname: search\ndescription: Search\n---\noperator-edit",
        encoding="utf-8",
    )

    materialize.write_home(materialize.agent_file_from_store(agent), source_agent=agent)

    assert "operator-edit" in local_copy.read_text(encoding="utf-8")
    assert skill_admin_store.get_drift(agent.id, "search")["drift"] == 1


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


def test_agent_file_from_store_exports_xfleetent_extension_fields(db):
    """服务级 degrade_mode/file_root/file_isolation 来自服务定义,approval_rules 来自该 agent
    的绑定;全默认(服务无非默认字段 + 绑定无规则)不产出 x-fleetent。"""
    agent = agent_store.create_agent("support", "p", [], mcp_server_ids=["docs", "plain"])
    agent_mcp_server_store.add_mcp_server(
        None,
        "docs",
        transport="http",
        url="https://docs.acme.internal/mcp",
        degrade_mode="strict",
        file_root="/exchange/docs",
        file_isolation="off",
    )
    agent_mcp_server_store.add_mcp_server(
        None, "plain", transport="http", url="https://plain.acme.internal/mcp"
    )
    agent_store.bind_mcp_server(agent.id, "docs")
    agent_store.bind_mcp_server(agent.id, "plain")
    # approval_rules is configured on the binding, not the server definition.
    agent_store.set_agent_mcp_approval_rules(
        agent.id, "docs", [{"tool": "manage_email", "when": {"operation": ["send"]}}]
    )

    exported = materialize.agent_file_from_store(agent_store.get_by_name("support"))
    servers = {server.id: server for server in exported.mcp_servers}
    assert servers["docs"].degrade_mode == "strict"
    assert servers["docs"].file_root == "/exchange/docs"
    assert servers["docs"].file_isolation == "off"
    assert [rule.model_dump() for rule in servers["docs"].approval_rules] == [
        {"tool": "manage_email", "when": {"operation": ["send"]}}
    ]

    payload = materialize.desired_state_payload_from_agent_file(exported)
    docs_ext = payload["mcpServers"]["docs"]["x-fleetent"]
    assert docs_ext["degrade_mode"] == "strict"
    assert docs_ext["file_root"] == "/exchange/docs"
    assert docs_ext["file_isolation"] == "off"
    assert docs_ext["approval_rules"] == [{"tool": "manage_email", "when": {"operation": ["send"]}}]
    assert "x-fleetent" not in payload["mcpServers"]["plain"]


def test_approval_rules_are_per_agent_binding(db):
    """同一 server 被两个 agent 绑定,各自 agent.yaml 只反映自己绑定的 approval_rules。"""
    a = agent_store.create_agent("agent-a", "p", [], mcp_server_ids=["mailer"])
    b = agent_store.create_agent("agent-b", "p", [], mcp_server_ids=["mailer"])
    agent_mcp_server_store.add_mcp_server(
        None, "mailer", transport="http", url="https://mailer.internal/mcp"
    )
    agent_store.bind_mcp_server(a.id, "mailer")
    agent_store.bind_mcp_server(b.id, "mailer")
    agent_store.set_agent_mcp_approval_rules(a.id, "mailer", [{"tool": "send_email", "when": None}])

    payload_a = materialize.desired_state_payload_from_agent_file(
        materialize.agent_file_from_store(agent_store.get_by_name("agent-a"))
    )
    payload_b = materialize.desired_state_payload_from_agent_file(
        materialize.agent_file_from_store(agent_store.get_by_name("agent-b"))
    )
    assert payload_a["mcpServers"]["mailer"]["x-fleetent"]["approval_rules"] == [
        {"tool": "send_email", "when": None}
    ]
    # agent-b never configured rules -> its mailer has no x-fleetent block at all.
    assert "x-fleetent" not in payload_b["mcpServers"]["mailer"]
