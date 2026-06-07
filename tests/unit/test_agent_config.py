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
        "mcp_servers": [
            {
                "id": "acme",
                "transport": "http",
                "url": "https://acme.internal/mcp",
                "auth_type": "bearer",
                "api_key_env": "ACME_MCP_TOKEN",
            }
        ],
        "bindings": {
            "default": False,
            "channels": ["slack:C0123"],
            "users": ["u_alice"],
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
    assert af.bindings.channels == ["slack:C0123"]
    assert af.bindings.users == ["u_alice"]
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
    assert af.bindings.default is False
    assert af.bindings.channels == []
    assert af.bindings.users == []


def test_agent_file_requires_models() -> None:
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate({"name": "bare", "version": 1})


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
    agent_dir = root / name
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_build_index_maps_names_channels_users_default(tmp_path) -> None:
    _write_agent(
        tmp_path,
        "support",
        bindings={"channels": ["slack:C123"], "users": ["u_alice"]},
    )
    _write_agent(
        tmp_path,
        "sales",
        bindings={"default": True, "channels": ["telegram:-100"], "users": ["u_bob"]},
    )
    index = agent_config.build_index(tmp_path)

    assert index.get("support").name == "support"
    assert index.get("sales").name == "sales"
    assert index.get("ghost") is None

    assert index.agent_for_channel("slack", "C123") == "support"
    assert index.agent_for_channel("telegram", "-100") == "sales"
    assert index.agent_for_channel("slack", "nope") is None

    assert index.agent_for_user("u_alice") == "support"
    assert index.agent_for_user("u_bob") == "sales"
    assert index.agent_for_user("nobody") is None

    assert index.default_agent() == "sales"


def test_build_index_missing_dir_is_empty(tmp_path) -> None:
    index = agent_config.build_index(tmp_path / "does-not-exist")
    assert index.get("anything") is None
    assert index.default_agent() is None


def test_build_index_empty_dir_is_empty(tmp_path) -> None:
    index = agent_config.build_index(tmp_path)
    assert index.default_agent() is None
    assert index.agent_for_channel("slack", "C1") is None


def test_build_index_dir_name_mismatch_fails_fast(tmp_path) -> None:
    bad = tmp_path / "helpdesk"
    bad.mkdir()
    (bad / "agent.yaml").write_text(yaml.safe_dump(_valid_doc()), encoding="utf-8")
    with pytest.raises(ValueError):
        agent_config.build_index(tmp_path)


def test_scan_sets_current_index(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(tmp_path))
    _write_agent(tmp_path, "support", bindings={"default": True})
    agent_config.scan()
    assert agent_config.current().get("support").name == "support"
    assert agent_config.current().default_agent() == "support"


# ── conflict detection (§2.3) ─────────────────────────────────────────────────


def test_duplicate_channel_binding_fails_fast(tmp_path) -> None:
    _write_agent(tmp_path, "support", bindings={"channels": ["slack:C123"]})
    _write_agent(tmp_path, "sales", bindings={"channels": ["slack:C123"]})
    with pytest.raises(ValueError) as exc:
        agent_config.build_index(tmp_path)
    msg = str(exc.value)
    assert "slack:C123" in msg
    assert "support" in msg and "sales" in msg


def test_duplicate_user_binding_fails_fast(tmp_path) -> None:
    _write_agent(tmp_path, "support", bindings={"users": ["u_alice"]})
    _write_agent(tmp_path, "sales", bindings={"users": ["u_alice"]})
    with pytest.raises(ValueError) as exc:
        agent_config.build_index(tmp_path)
    assert "u_alice" in str(exc.value)


def test_multiple_default_agents_fails_fast(tmp_path) -> None:
    _write_agent(tmp_path, "support", bindings={"default": True})
    _write_agent(tmp_path, "sales", bindings={"default": True})
    with pytest.raises(ValueError) as exc:
        agent_config.build_index(tmp_path)
    msg = str(exc.value)
    assert "support" in msg and "sales" in msg


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
            "connectors": {"telegram": {"bot_token_env": "SALES_TG_BOT", "channels": ["-100123"]}},
        }
    )
    assert af.connectors.telegram is not None
    assert af.connectors.telegram.bot_token_env == "SALES_TG_BOT"
    assert af.connectors.telegram.channels == ["-100123"]


def test_telegram_agents_lists_declaring_agents(tmp_path) -> None:
    _write_agent(tmp_path, "sales", connectors={"telegram": {"bot_token_env": "SALES_TG_BOT"}})
    _write_agent(tmp_path, "plain")  # no telegram connector
    index = agent_config.build_index(tmp_path)
    assert index.telegram_agents() == ["sales"]


def test_inline_secret_in_telegram_rejected(tmp_path) -> None:
    _write_agent(
        tmp_path,
        "sales",
        connectors={"telegram": {"bot_token_env": "123456789:AAHinlineLiveBotTokenXXXXXXXX"}},
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
    agents_dir = home / "agents"
    agents_dir.mkdir(parents=True)
    _write_agent(agents_dir, "other")
    # Default Agent home file, bindings.default false -> still forced default.
    default_home = home / "agents" / "default"
    _write_config_agent(
        default_home, "default", bindings={"default": False, "channels": ["slack:C9"]}
    )
    monkeypatch.setenv("FLEETENT_HOME", str(home))

    index = agent_config.build_index()

    assert set(index.agents) == {"default"}  # multi-scan ignored
    assert index.default == "default"  # forced default
    assert index.by_channel.get("slack:C9") == "default"
    assert index.get("other") is None


def test_build_index_falls_back_to_multiscan_without_config_agent_file(
    tmp_path, monkeypatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, "a", bindings={"default": True})
    _write_agent(agents_dir, "b")
    monkeypatch.setenv("FLEETENT_HOME", str(home))  # no default agent home file
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(agents_dir))  # explicit multi-scan dir

    index = agent_config.build_index()

    assert set(index.agents) == {"a", "b"}
    assert index.default == "a"  # multiscan: default decided by bindings.default


def test_build_index_ignores_old_home_root_agent_yaml(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    _write_config_agent(home, "legacy")
    monkeypatch.setenv("FLEETENT_HOME", str(home))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)

    index = agent_config.build_index()

    assert index.agents == {}
    assert index.default is None


def test_repo_agent_yaml_example_loads_as_single_agent_file() -> None:
    """The shipped single-agent template parses with the single-file loader."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    example = repo / "agents" / "default" / "agent.yaml.example"
    assert example.is_file(), "agents/default/agent.yaml.example must exist (installer template)"
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
