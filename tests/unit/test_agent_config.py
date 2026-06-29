"""Unit tests for the file-driven agent config loader (file-agent-runtime)."""

import pytest
import yaml
from pydantic import ValidationError

from fleetent import agent_config


def _valid_doc() -> dict:
    return {
        "name": "support",
        "version": 7,
        "tenant_id": "acme",
        "team_id": "t1",
        "system_prompt": "You are support.",
        "models": _valid_models_doc(),
        "memory_namespace": "support",
        "skills_dir": "skills",
        "allowed_skills": ["triage"],
        "allowed_tools": ["search_*", "acme__*"],
        "plugins": ["acme"],
        "features": {"code_execution": True},
        "mcpServers": {
            "acme": {
                "transport": "http",
                "url": "https://acme.internal/mcp",
                "auth_type": "bearer",
                "api_key_env": "ACME_MCP_TOKEN",
            }
        },
    }


def _valid_models_doc() -> dict:
    return {
        "targets": [
            {
                "id": "primary",
                "provider": "anthropic",
                "protocol": "openai_chat",
                "base_url": "https://api.anthropic.com/v1/",
                "model": "claude-sonnet-4-5",
                "api_key_env": "FLEETENT_MODEL_PRIMARY_API_KEY",
                "max_tokens": 4096,
                "params": {"temperature": 0.5},
            },
            {
                "id": "embed",
                "provider": "local",
                "protocol": "http_embedding",
                "endpoint": "http://embedding.local/embed",
            },
        ],
        "routes": {
            "default": [{"target": "primary"}],
            "memory_extraction": [
                {"target": "primary", "max_tokens": 1024, "params": {"temperature": 0}}
            ],
            "embedding": [{"target": "embed"}],
        },
    }


def test_agent_file_parses_all_fields() -> None:
    af = agent_config.AgentFile.model_validate(_valid_doc())
    assert af.name == "support"
    assert af.version == 7
    assert af.tenant_id == "acme"
    assert af.team_id == "t1"
    assert af.allowed_tools == ["search_*", "acme__*"]
    assert af.plugins == ["acme"]
    assert af.features == {"code_execution": True}
    assert af.models.targets[0].id == "primary"
    assert af.models.routes["memory_extraction"][0].max_tokens == 1024
    # inline mcp_servers reuse the config McpServerSettings model
    assert len(af.mcp_servers) == 1
    assert af.mcp_servers[0].id == "acme"
    assert af.mcp_servers[0].api_key_env == "ACME_MCP_TOKEN"


def test_agent_file_defaults() -> None:
    af = agent_config.AgentFile.model_validate(
        {"name": "bare", "version": 1, "models": _valid_models_doc()}
    )
    assert af.skills_dir is None
    assert af.allowed_skills == []
    assert af.plugins == []
    assert af.allowed_tools == []
    assert af.mcp_servers == []
    assert af.features == {}
    assert af.tenant_id == "default"
    assert af.team_id is None


def test_agent_file_requires_models() -> None:
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate({"name": "bare", "version": 1})


# --- sandbox-workspace-scope-split: per-agent image persistence schema ------


def test_sandbox_settings_image_persistence_defaults_off() -> None:
    """Defaults keep prior behaviour: image persistence off, no setup_command."""
    af = agent_config.AgentFile.model_validate(
        {"name": "bare", "version": 1, "models": _valid_models_doc()}
    )
    assert af.sandbox.image_persistence is False
    assert af.sandbox.setup_command is None


def test_sandbox_settings_image_persistence_parsed() -> None:
    doc = _valid_doc()
    doc["sandbox"] = {
        "image_persistence": True,
        "setup_command": "pip install requests pandas",
    }
    af = agent_config.AgentFile.model_validate(doc)
    assert af.sandbox.image_persistence is True
    assert af.sandbox.setup_command == "pip install requests pandas"


def test_sandbox_settings_rejects_unknown_key() -> None:
    """extra='forbid': an unknown sandbox subkey is rejected (typo never silent)."""
    doc = _valid_doc()
    doc["sandbox"] = {"image_persistance": True}  # typo
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_sandbox_settings_rejects_non_bool_image_persistence() -> None:
    doc = _valid_doc()
    doc["sandbox"] = {"image_persistence": ["not", "a", "bool"]}
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


# --- sandbox-scope-split-followups: explicit multi_user signal --------------


def test_sandbox_settings_multi_user_defaults_on() -> None:
    """Fail-safe default: multi_user is True (every agent treated as multi-user;
    single-user agent-scope data reuse requires explicit opt-out)."""
    af = agent_config.AgentFile.model_validate(
        {"name": "bare", "version": 1, "models": _valid_models_doc()}
    )
    assert af.sandbox.multi_user is True


def test_sandbox_settings_multi_user_explicit_opt_out() -> None:
    """Explicit `multi_user: false` opts a single-user deployment back out."""
    doc = {"name": "bare", "version": 1, "models": _valid_models_doc()}
    doc["sandbox"] = {"multi_user": False}
    af = agent_config.AgentFile.model_validate(doc)
    assert af.sandbox.multi_user is False


def test_sandbox_settings_multi_user_parsed() -> None:
    doc = _valid_doc()
    doc["sandbox"] = {"multi_user": True}
    af = agent_config.AgentFile.model_validate(doc)
    assert af.sandbox.multi_user is True


def test_sandbox_settings_rejects_non_bool_multi_user() -> None:
    doc = _valid_doc()
    doc["sandbox"] = {"multi_user": "yes-please"}
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_sandbox_settings_unknown_key_still_rejected_with_multi_user() -> None:
    """extra='forbid' keeps rejecting unknown keys after multi_user is added."""
    doc = _valid_doc()
    doc["sandbox"] = {"multi_user": True, "multi_users": True}  # typo
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


@pytest.mark.parametrize("field", ["provider", "protocol"])
def test_model_target_requires_provider_and_protocol(field: str) -> None:
    doc = _valid_doc()
    del doc["models"]["targets"][0][field]
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_model_target_duplicate_id_rejected() -> None:
    doc = _valid_doc()
    doc["models"]["targets"].append(dict(doc["models"]["targets"][0]))
    with pytest.raises(ValidationError, match="duplicate target id"):
        agent_config.AgentFile.model_validate(doc)


def test_model_route_missing_target_rejected() -> None:
    doc = _valid_doc()
    doc["models"]["routes"]["default"] = [{"target": "missing"}]
    with pytest.raises(ValidationError, match="unknown model target"):
        agent_config.AgentFile.model_validate(doc)


def test_model_api_key_env_inline_secret_rejected(tmp_path) -> None:
    doc = _valid_doc()
    doc["models"]["targets"][0]["api_key_env"] = "sk-live-0123456789abcdefghijABCDEF"
    path = tmp_path / "agent.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="api_key_env"):
        agent_config.load_agent_home_file(path)


def test_model_overrides_old_field_rejected() -> None:
    doc = _valid_doc()
    doc["model_overrides"] = {"default": {"model": "legacy"}}
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_agent_file_accepts_typed_intelligence_config() -> None:
    doc = _valid_doc()
    doc.update(
        {
            "vector_store": {"backend": "sqlite", "database_url": "sqlite:///data/vector.db"},
            "embedding": {
                "backend": "http",
                "dimensions": 1024,
                "endpoint_env": "FLEETENT_EVAL_EMBEDDING_ENDPOINT",
                "model_env": "FLEETENT_EVAL_EMBEDDING_MODEL",
                "api_key_env": "FLEETENT_EVAL_EMBEDDING_API_KEY",
            },
            "rerank": {
                "backend": "http",
                "endpoint_env": "FLEETENT_EVAL_RERANK_ENDPOINT",
                "model_env": "FLEETENT_EVAL_RERANK_MODEL",
                "api_key_env": "FLEETENT_EVAL_RERANK_API_KEY",
            },
            "knowledge": {
                "enabled": True,
                "bindings": [
                    {
                        "tenant_id": "pilot-tenant",
                        "kb_id": "pilot-kb",
                        "default": True,
                        "permissions": {"search": True},
                    }
                ],
                "retrieval_policy": {
                    "mode": "hybrid",
                    "top_k": 12,
                    "rerank": True,
                    "embedding_route": "embedding",
                    "rerank_route": "rerank",
                },
            },
            "long_term_ctx": {
                "max_tokens": 2048,
                "memory_max_tokens": 1024,
                "knowledge_max_tokens": 1024,
                "conflict_preference": "auto",
            },
        }
    )

    af = agent_config.AgentFile.model_validate(doc)

    assert af.vector_store.backend == "sqlite"
    assert af.embedding.dimensions == 1024
    assert af.embedding.api_key_env == "FLEETENT_EVAL_EMBEDDING_API_KEY"
    assert af.rerank.model_env == "FLEETENT_EVAL_RERANK_MODEL"
    assert af.knowledge.bindings[0].tenant_id == "pilot-tenant"
    assert af.knowledge.bindings[0].kb_id == "pilot-kb"
    assert af.knowledge.bindings[0].default is True
    assert af.knowledge.retrieval_policy.mode == "hybrid"
    assert af.knowledge.retrieval_policy.top_k == 12
    assert af.knowledge.retrieval_policy.embedding_route == "embedding"
    assert af.knowledge.retrieval_policy.rerank_route == "rerank"
    assert af.long_term_ctx.conflict_preference == "auto"


def test_agent_file_rejects_old_knowledge_base_connector_config() -> None:
    doc = {
        "name": "pilot",
        "version": 1,
        "models": _valid_models_doc(),
        "knowledge_base": {
            "enabled": True,
            "google_drive": {
                "connectors": [
                    {
                        "connector_id": "pilot-drive",
                        "tenant_id": "pilot-tenant",
                        "kb_id": "pilot-kb",
                        "folder_id": "1Cs7y_5p8BOX4hZ7CT7fbS8CPBCkjF-W3",
                        "access_token_env": "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN",
                        "refresh_token_env": "FLEETENT_GOOGLE_DRIVE_REFRESH_TOKEN",
                        "client_id_env": "FLEETENT_GOOGLE_DRIVE_CLIENT_ID",
                        "client_secret_env": "FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET",
                    }
                ]
            },
        },
    }

    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_agent_knowledge_enabled_requires_binding() -> None:
    with pytest.raises(ValidationError, match="bindings"):
        agent_config.AgentFile.model_validate(
            {
                "name": "pilot",
                "version": 1,
                "models": _valid_models_doc(),
                "knowledge": {"enabled": True},
            }
        )


def test_agent_knowledge_rejects_duplicate_defaults() -> None:
    with pytest.raises(ValidationError, match="default"):
        agent_config.AgentFile.model_validate(
            {
                "name": "pilot",
                "version": 1,
                "models": _valid_models_doc(),
                "knowledge": {
                    "enabled": True,
                    "bindings": [
                        {"tenant_id": "tenant-a", "kb_id": "support", "default": True},
                        {"tenant_id": "tenant-a", "kb_id": "billing", "default": True},
                    ],
                },
            }
        )


def test_agent_knowledge_rejects_cross_tenant_bindings() -> None:
    with pytest.raises(ValidationError, match="same tenant_id"):
        agent_config.AgentFile.model_validate(
            {
                "name": "pilot",
                "version": 1,
                "models": _valid_models_doc(),
                "knowledge": {
                    "enabled": True,
                    "bindings": [
                        {"tenant_id": "tenant-a", "kb_id": "support", "default": True},
                        {"tenant_id": "tenant-b", "kb_id": "billing"},
                    ],
                },
            }
        )


def test_agent_knowledge_exposes_shared_tenant_id_for_valid_bindings() -> None:
    agent = agent_config.AgentFile.model_validate(
        {
            "name": "pilot",
            "version": 1,
            "models": _valid_models_doc(),
            "knowledge": {
                "enabled": True,
                "bindings": [
                    {"tenant_id": "tenant-a", "kb_id": "support", "default": True},
                    {"tenant_id": "tenant-a", "kb_id": "billing"},
                ],
            },
        }
    )

    assert agent.knowledge.tenant_id == "tenant-a"


def test_agent_knowledge_retrieval_policy_use_planner_defaults_false_and_parses() -> None:
    default_agent = agent_config.AgentFile.model_validate(
        {
            "name": "pilot",
            "version": 1,
            "models": _valid_models_doc(),
            "knowledge": {
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "support", "default": True}],
            },
        }
    )

    assert default_agent.knowledge.retrieval_policy.use_planner is False

    parsed_agent = agent_config.AgentFile.model_validate(
        {
            "name": "pilot",
            "version": 1,
            "models": _valid_models_doc(),
            "knowledge": {
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "support", "default": True}],
                "retrieval_policy": {"mode": "hybrid", "use_planner": True},
            },
        }
    )

    assert parsed_agent.knowledge.retrieval_policy.use_planner is True


def test_agent_knowledge_provider_defaults_to_local() -> None:
    agent = agent_config.AgentFile.model_validate(
        {
            "name": "pilot",
            "version": 1,
            "models": _valid_models_doc(),
            "knowledge": {
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "support", "default": True}],
            },
        }
    )

    assert agent.knowledge.provider.type == "local"
    assert agent.knowledge.provider.url is None
    assert agent.knowledge.provider.auth_ref is None


def test_agent_knowledge_provider_http_parses_url_and_auth_ref() -> None:
    agent = agent_config.AgentFile.model_validate(
        {
            "name": "pilot",
            "version": 1,
            "models": _valid_models_doc(),
            "knowledge": {
                "enabled": True,
                "bindings": [{"tenant_id": "tenant-a", "kb_id": "support", "default": True}],
                "provider": {
                    "type": "http",
                    "url": "https://kb.example/search",
                    "auth_ref": "env:FLEETENT_KB_SERVICE_KEY",
                },
            },
        }
    )

    assert agent.knowledge.provider.type == "http"
    assert agent.knowledge.provider.url == "https://kb.example/search"
    assert agent.knowledge.provider.auth_ref == "env:FLEETENT_KB_SERVICE_KEY"


@pytest.mark.parametrize("missing", ["tenant_id", "kb_id"])
def test_agent_knowledge_binding_requires_tenant_and_kb(missing: str) -> None:
    binding = {"tenant_id": "tenant-a", "kb_id": "support"}
    del binding[missing]
    with pytest.raises(ValidationError, match=missing):
        agent_config.AgentFile.model_validate(
            {
                "name": "pilot",
                "version": 1,
                "models": _valid_models_doc(),
                "knowledge": {"enabled": True, "bindings": [binding]},
            }
        )


def test_load_agent_home_file_rejects_old_knowledge_base_connector_config(tmp_path) -> None:
    doc = {
        "name": "pilot",
        "version": 1,
        "models": _valid_models_doc(),
        "knowledge_base": {
            "google_drive": {
                "connectors": [
                    {
                        "connector_id": "pilot-drive",
                        "tenant_id": "pilot-tenant",
                        "kb_id": "pilot-kb",
                        "folder_id": "1Cs7y_5p8BOX4hZ7CT7fbS8CPBCkjF-W3",
                    }
                ]
            },
        },
    }
    path = tmp_path / "agent.yaml"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    with pytest.raises(ValidationError):
        agent_config.load_agent_home_file(path)


@pytest.mark.parametrize("missing", ["name", "version"])
def test_agent_file_missing_required_rejected(missing: str) -> None:
    doc = _valid_doc()
    del doc[missing]
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_agent_file_unknown_field_rejected() -> None:
    doc = _valid_doc()
    doc["surprise"] = "nope"
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_load_agent_file_reads_yaml(tmp_path) -> None:
    agent_dir = tmp_path / "support"
    agent_dir.mkdir()
    (agent_dir / "agent.yaml").write_text(yaml.safe_dump(_valid_doc()), encoding="utf-8")
    af = agent_config.load_agent_file(agent_dir)
    assert af.name == "support"
    assert af.version == 7


def test_load_agent_file_dir_name_mismatch_rejected(tmp_path) -> None:
    agent_dir = tmp_path / "helpdesk"
    agent_dir.mkdir()
    # in-file name is "support" but the directory is "helpdesk"
    (agent_dir / "agent.yaml").write_text(yaml.safe_dump(_valid_doc()), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        agent_config.load_agent_file(agent_dir)
    assert "helpdesk" in str(exc.value)
    assert "support" in str(exc.value)


# ── scan + index (§2) ─────────────────────────────────────────────────────────


def _write_agent(root, name: str, **overrides) -> None:
    doc = {"name": name, "version": 1, "models": _valid_models_doc()}
    doc.update(overrides)
    # Emit the standard map-keyed form; tests keep the legacy list shape for brevity.
    if isinstance(doc.get("mcp_servers"), list):
        doc["mcpServers"] = {
            e["id"]: {k: v for k, v in e.items() if k != "id"} for e in doc.pop("mcp_servers")
        }
    agent_dir = root / name
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_build_index_maps_names_and_default(tmp_path) -> None:
    _write_agent(tmp_path, "support")
    _write_agent(tmp_path, "sales")
    index = agent_config.build_index(tmp_path)

    assert index.get("support").name == "support"
    assert index.get("sales").name == "sales"
    assert index.get("ghost") is None


def test_build_index_missing_dir_is_empty(tmp_path) -> None:
    index = agent_config.build_index(tmp_path / "does-not-exist")
    assert index.get("anything") is None
    assert index.default_agent() is None


def test_build_index_empty_dir_is_empty(tmp_path) -> None:
    index = agent_config.build_index(tmp_path)
    assert index.default_agent() is None


def test_build_index_dir_name_mismatch_fails_fast(tmp_path) -> None:
    bad = tmp_path / "helpdesk"
    bad.mkdir()
    (bad / "agent.yaml").write_text(yaml.safe_dump(_valid_doc()), encoding="utf-8")
    with pytest.raises(ValueError):
        agent_config.build_index(tmp_path)


def test_scan_sets_current_index(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(tmp_path))
    _write_agent(tmp_path, "support")
    agent_config.scan()
    assert agent_config.current().get("support").name == "support"


# ── secret rejection (§2.5) ───────────────────────────────────────────────────


def test_inline_secret_in_mcp_rejected(tmp_path) -> None:
    # An mcp_servers entry that puts a live token where an env reference belongs.
    _write_agent(
        tmp_path,
        "support",
        mcp_servers=[{"id": "acme", "api_key_env": "sk-live-0123456789abcdefghijABCDEF"}],
    )
    with pytest.raises(ValueError) as exc:
        agent_config.build_index(tmp_path)
    msg = str(exc.value)
    assert "support" in msg
    assert "api_key_env" in msg


def test_env_reference_accepted(tmp_path) -> None:
    _write_agent(
        tmp_path,
        "support",
        mcp_servers=[{"id": "acme", "api_key_env": "ACME_MCP_TOKEN"}],
    )
    index = agent_config.build_index(tmp_path)  # no raise
    assert index.get("support").mcp_servers[0].api_key_env == "ACME_MCP_TOKEN"


def test_agent_file_parses_telegram_connector() -> None:
    af = agent_config.AgentFile.model_validate(
        {
            "name": "sales",
            "version": 1,
            "models": _valid_models_doc(),
            "im": {"telegram": {"bot_token_env": "SALES_TG_BOT"}},
        }
    )
    assert af.im.telegram is not None
    assert af.im.telegram.bot_token_env == "SALES_TG_BOT"


def test_telegram_agents_lists_declaring_agents(tmp_path) -> None:
    _write_agent(tmp_path, "sales", im={"telegram": {"bot_token_env": "SALES_TG_BOT"}})
    _write_agent(tmp_path, "plain")  # no telegram connector
    index = agent_config.build_index(tmp_path)
    assert index.telegram_agents() == ["sales"]


def test_inline_secret_in_telegram_rejected(tmp_path) -> None:
    _write_agent(
        tmp_path,
        "sales",
        im={"telegram": {"bot_token_env": "123456789:AAHinlineLiveBotTokenXXXXXXXX"}},
    )
    with pytest.raises(ValueError) as exc:
        agent_config.build_index(tmp_path)
    msg = str(exc.value)
    assert "sales" in msg
    assert "bot_token_env" in msg


def test_long_system_prompt_not_flagged_as_secret(tmp_path) -> None:
    # The secret scan targets MCP/connector defs, not free-text prompts.
    _write_agent(
        tmp_path,
        "support",
        system_prompt="You are a helpful assistant with supercalifragilisticexpialidocious skills.",
    )
    index = agent_config.build_index(tmp_path)  # no raise
    assert index.get("support") is not None


# ── default Agent home config ────────────────────────────────────────────────


def _write_config_agent(home, name: str, **overrides) -> None:
    """Write a single agent.yaml at the provided home-like directory."""
    doc = {"name": name, "version": 1, "models": _valid_models_doc()}
    doc.update(overrides)
    home.mkdir(parents=True, exist_ok=True)
    (home / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_load_single_agent_file_skips_dir_name_check(tmp_path) -> None:
    # Config-dir single-agent file: `name` need not match any directory name.
    _write_config_agent(tmp_path, "whatever-name")
    agent = agent_config.load_agent_home_file(tmp_path / "agent.yaml")
    assert agent.name == "whatever-name"


def test_load_single_agent_file_still_rejects_inline_secret(tmp_path) -> None:
    _write_config_agent(
        tmp_path,
        "support",
        mcp_servers=[
            {
                "id": "acme",
                "transport": "http",
                "url": "https://acme.internal/mcp",
                "auth_type": "bearer",
                "api_key_env": "xoxb-1234567890-abcdefABCDEF",  # looks like a real secret
            }
        ],
    )
    with pytest.raises(ValueError):
        agent_config.load_agent_home_file(tmp_path / "agent.yaml")


def test_build_index_prefers_default_agent_home_as_sole_default(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    # Another agent also exists; it must be ignored when the default Agent home is present.
    agents_dir = home / "tenants" / "default" / "agents"
    agents_dir.mkdir(parents=True)
    _write_agent(agents_dir, "other")
    # Default Agent home file: still forced default regardless.
    default_home = home / "tenants" / "default" / "agents" / "default"
    _write_config_agent(default_home, "default")
    monkeypatch.setenv("FLEETENT_HOME", str(home))

    index = agent_config.build_index()

    assert set(index.agents) == {"default"}  # multi-scan ignored
    assert index.default == "default"  # forced default
    assert index.get("other") is None


def test_build_index_falls_back_to_multiscan_without_config_agent_file(
    tmp_path, monkeypatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, "a")
    _write_agent(agents_dir, "b")
    monkeypatch.setenv("FLEETENT_HOME", str(home))  # no default agent home file
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(agents_dir))  # explicit multi-scan dir

    index = agent_config.build_index()

    assert set(index.agents) == {"a", "b"}


def test_build_index_ignores_old_home_root_agent_yaml(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _write_config_agent(home, "legacy")
    monkeypatch.setenv("FLEETENT_HOME", str(home))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    # AGENTS_DIR is evaluated at import time; patch it so _resolve_agents_dir picks up the
    # isolated tmp directory instead of the real ~/.fleetent/agents.
    monkeypatch.setattr(agent_config, "AGENTS_DIR", home / "tenants" / "default" / "agents")

    index = agent_config.build_index()

    assert index.agents == {}
    assert index.default is None


def test_repo_agent_yaml_example_loads_as_single_agent_file() -> None:
    """The shipped single-agent template parses with the single-file loader."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    example = repo / "agent.yaml.example"
    assert example.is_file(), "agent.yaml.example must exist at repo root (installer template)"
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))
    assert "knowledge_base" not in raw
    agent = agent_config.load_agent_home_file(example)
    assert agent.name  # non-empty
    assert agent.version >= 1
    assert agent.models.routes["default"][0].target == "primary"
    assert agent.models.targets[0].api_key_env == "FLEETENT_MODEL_PRIMARY_API_KEY"
    assert agent.vector_store.backend == "sqlite"
    assert agent.embedding.api_key_env == "FLEETENT_EMBED_API_KEY"
    assert agent.rerank.api_key_env == "FLEETENT_RERANK_API_KEY"
    assert agent.knowledge.enabled is True
    assert agent.knowledge.bindings[0].kb_id == "pilot-kb"


# ── dead-field removal tests ──────────────────────────────────────────────────


def test_microsandbox_url_rejected() -> None:
    """microsandbox_url is a dead field and must be rejected (extra='forbid')."""
    doc = _valid_doc()
    doc["microsandbox_url"] = "http://host.docker.internal:7777"
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_image_gen_url_rejected() -> None:
    doc = _valid_doc()
    doc["image_gen_url"] = "http://localhost:9004/v1/images/generations"
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_image_gen_model_rejected() -> None:
    doc = _valid_doc()
    doc["image_gen_model"] = "flux-schnell"
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_vision_url_rejected() -> None:
    doc = _valid_doc()
    doc["vision_url"] = "http://localhost:9005/v1"
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_vision_model_rejected() -> None:
    doc = _valid_doc()
    doc["vision_model"] = "llava"
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_permission_gate_enabled_default_true() -> None:
    agent = agent_config.AgentFile.model_validate(_valid_doc())
    assert agent.permission_gate_enabled is True


def test_permission_gate_enabled_false() -> None:
    doc = _valid_doc()
    doc["permission_gate_enabled"] = False
    agent = agent_config.AgentFile.model_validate(doc)
    assert agent.permission_gate_enabled is False


# --- collect_env_var_names (task 1.1 / D2 shared collector) ---


def _make_agent_with_all_env_fields() -> agent_config.AgentFile:
    """AgentFile referencing env vars in every category that flatten must catch."""
    from fleetent.config import McpServerSettings

    return agent_config.AgentFile(
        name="full-env-agent",
        version=1,
        system_prompt="test",
        models=agent_config.AgentModels(
            targets=[
                agent_config.ModelTarget(
                    id="primary",
                    provider="anthropic",
                    protocol="openai_chat",
                    base_url="https://api.anthropic.com/v1/",
                    model="claude-opus-4-8",
                    api_key_env="MODEL_API_KEY",
                ),
                agent_config.ModelTarget(
                    id="emb",
                    provider="local",
                    protocol="http_embedding",
                    endpoint="http://localhost:11434/v1/embeddings",
                    api_key_env="EMBEDDING_API_KEY",
                ),
                agent_config.ModelTarget(
                    id="rer",
                    provider="local",
                    protocol="http_rerank",
                    endpoint="http://localhost:11434/v1/rerank",
                    api_key_env="RERANK_API_KEY",
                ),
            ],
            routes={
                "default": [agent_config.ModelRouteEntry(target="primary")],
                "embedding": [agent_config.ModelRouteEntry(target="emb")],
                "rerank": [agent_config.ModelRouteEntry(target="rer")],
            },
        ),
        im=agent_config.ImBinding(
            telegram=agent_config.TelegramBinding(bot_token_env="TELEGRAM_BOT_TOKEN"),
        ),
        mcp_servers=[
            McpServerSettings(
                id="acme",
                transport="http",
                url="https://mcp.example.com",
                auth_type="bearer",
                api_key_env="ACME_MCP_TOKEN",
            )
        ],
    )


def test_collect_env_var_names_returns_all_referenced_names() -> None:
    agent = _make_agent_with_all_env_fields()

    names = agent_config.collect_env_var_names(agent)

    assert "MODEL_API_KEY" in names
    assert "EMBEDDING_API_KEY" in names
    assert "RERANK_API_KEY" in names
    assert "TELEGRAM_BOT_TOKEN" in names
    assert "ACME_MCP_TOKEN" in names
    # must be deduplicated and stable-ordered
    assert names == sorted(set(names))


def test_collect_env_var_names_includes_mcp_env_and_headers_env_refs() -> None:
    from fleetent.config import McpServerSettings

    agent = agent_config.AgentFile(
        name="mcp-env-ref-agent",
        version=1,
        system_prompt="test",
        models={
            "targets": [
                {
                    "id": "primary",
                    "provider": "anthropic",
                    "protocol": "openai_chat",
                    "base_url": "https://api.anthropic.com/v1/",
                    "model": "claude-opus-4-8",
                    "api_key_env": "MODEL_API_KEY",
                }
            ],
            "routes": {"default": [{"target": "primary"}]},
        },
        mcp_servers=[
            McpServerSettings(
                id="stdio-docs",
                transport="stdio",
                command="python",
                args=["server.py"],
                env={
                    "DB_URL": "env:MY_DATABASE_URL",
                    "STATIC_FLAG": "literal",
                    "SECOND_DB_URL": "env:MY_DATABASE_URL",
                },
            ),
            McpServerSettings(
                id="http-docs",
                transport="http",
                url="https://mcp.example.com",
                headers={
                    "Authorization": "env:MY_TOKEN",
                    "X-Plain": "literal",
                },
            ),
        ],
    )

    names = agent_config.collect_env_var_names(agent)

    assert "MODEL_API_KEY" in names
    assert "MY_DATABASE_URL" in names
    assert "MY_TOKEN" in names
    assert "literal" not in names
    assert names.count("MY_DATABASE_URL") == 1


# --- task 6.1: platform and node alignment ---


def test_platform_materialize_and_node_use_same_env_collector() -> None:
    """Both platform materialize._env_var_names and node referenced_env_names
    must produce identical output — they both delegate to collect_env_var_names."""
    from fleetent.platform.agent_lifecycle.materialize import _env_var_names as platform_env_names
    from fleetent.runtime.agent_init import referenced_env_names as node_env_names

    agent = _make_agent_with_all_env_fields()

    platform_result = platform_env_names(agent)
    node_result = node_env_names(agent)

    assert platform_result == node_result, (
        "platform._env_var_names and node.referenced_env_names diverged — "
        "both must delegate to collect_env_var_names"
    )
