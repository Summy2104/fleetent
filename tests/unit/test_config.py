from pathlib import Path

import pytest

from fleetent import paths
from fleetent.agent_config import AgentFile, default_models
from fleetent.config import Settings, configure_logging


@pytest.fixture(autouse=True)
def isolate_settings_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))


def test_settings_defaults():
    s = Settings()
    assert s.database_url == f"sqlite:///{paths.data_dir() / 'fleetent.db'}"
    assert s.log_format == "console"


# Agent-runtime fields dissolved into agent.yaml (dissolve-global-settings); the slim
# platform Settings MUST NOT carry governance / deployment / intelligence knobs.
_DISSOLVED_GOVERNANCE_FIELDS = {
    "permission_gate_medium_timeout_seconds",
    "permission_gate_high_timeout_seconds",
    "context_max_tokens",
    "context_compress_threshold",
    "context_keep_recent",
    "context_tmax_ratio",
    "context_tretained_ratio",
    "compression_initial_intent_max",
    "context_flap_window",
    "context_min_savings_ratio",
    "context_min_interval_turns",
    "agent_budget_session_turns",
    "agent_budget_session_tokens",
    "agent_budget_user_turns",
    "agent_budget_user_tokens",
    "agent_budget_agent_turns",
    "agent_budget_agent_tokens",
    "agent_budget_global_turns",
    "agent_budget_global_tokens",
    "agent_budget_user_window",
    "agent_budget_agent_window",
    "agent_budget_global_window",
    "session_ttl_days",
    "session_max_total_mb",
    "session_max_count",
    "session_cleanup_interval_seconds",
    "agent_max_turns",
    "agent_max_consecutive_failures",
    "agent_max_tokens",
    "agent_grace_call_token_ratio",
    "agent_grace_call_min_tokens",
    "sub_agent_timeout_seconds",
    "tool_default_timeout_seconds",
    "agent_loop_repeat_threshold",
    "guardrail_repeat_threshold",
    "agent_tool_parallel_max",
    "loop_detect_ignore_arg_keys",
    "provider_failure_threshold",
    "provider_cooldown_seconds",
}
_DISSOLVED_DEPLOYMENT_FIELDS = {
    "microsandbox_url",
    "image_gen_url",
    "image_gen_model",
    "vision_url",
    "vision_model",
    "disabled_skills",
    "diagnostics",
}
_DISSOLVED_INTELLIGENCE_FIELDS = {
    "vector_store",
    "embedding",
    "rerank",
    "long_term_ctx",
    "knowledge_base",
    "mcp",
    "scheduling",
    "webhooks",
}


def test_settings_excludes_dissolved_agent_runtime_fields():
    fields = set(Settings.model_fields)
    dissolved = (
        _DISSOLVED_GOVERNANCE_FIELDS | _DISSOLVED_DEPLOYMENT_FIELDS | _DISSOLVED_INTELLIGENCE_FIELDS
    )
    assert fields.isdisjoint(dissolved), sorted(fields & dissolved)


def test_settings_excludes_im_tokens_and_default_agent_and_api_key():
    fields = set(Settings.model_fields)
    removed = {
        "slack_bot_token",
        "slack_app_token",
        "telegram_bot_token",
        "default_agent_name",
        "anthropic_api_key",
    }
    assert fields.isdisjoint(removed), sorted(fields & removed)


def test_settings_constructible_without_any_secret():
    # Platform Settings carries no secret/API key; it builds with no arguments.
    s = Settings()
    assert s.log_format == "console"


def test_yaml_secret_fields_is_empty_safety_net():
    from fleetent.config import YAML_SECRET_FIELDS

    assert frozenset() == YAML_SECRET_FIELDS


def test_settings_loads_non_secret_values_from_settings_yaml(tmp_path, monkeypatch):
    import fleetent.config as cfg

    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text(
        "\n".join(
            [
                "database_url: sqlite:///tmp/fleetent.db",
                "log_format: json",
                "observability:",
                "  logging:",
                "    console_level: warning",
            ]
        )
    )
    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", settings_yaml)

    s = Settings()

    assert s.database_url == "sqlite:///tmp/fleetent.db"
    assert s.log_format == "json"
    assert s.observability.logging.console_level == "warning"


def test_vector_provider_settings_accept_env_references():
    s = AgentFile(
        name="t",
        version=1,
        models=default_models(),
        embedding={
            "backend": "http",
            "endpoint_env": "FLEETENT_EVAL_EMBEDDING_ENDPOINT",
            "model_env": "FLEETENT_EVAL_EMBEDDING_MODEL",
            "dimensions_env": "FLEETENT_EVAL_EMBEDDING_DIMENSIONS",
            "api_key_env": "FLEETENT_EVAL_EMBEDDING_API_KEY",
        },
        rerank={
            "backend": "http",
            "endpoint_env": "FLEETENT_EVAL_RERANK_ENDPOINT",
            "model_env": "FLEETENT_EVAL_RERANK_MODEL",
            "api_key_env": "FLEETENT_EVAL_RERANK_API_KEY",
        },
    )

    assert s.embedding.endpoint_env == "FLEETENT_EVAL_EMBEDDING_ENDPOINT"
    assert s.embedding.model_env == "FLEETENT_EVAL_EMBEDDING_MODEL"
    assert s.embedding.dimensions_env == "FLEETENT_EVAL_EMBEDDING_DIMENSIONS"
    assert s.embedding.api_key_env == "FLEETENT_EVAL_EMBEDDING_API_KEY"
    assert s.rerank.endpoint_env == "FLEETENT_EVAL_RERANK_ENDPOINT"
    assert s.rerank.model_env == "FLEETENT_EVAL_RERANK_MODEL"
    assert s.rerank.api_key_env == "FLEETENT_EVAL_RERANK_API_KEY"


def test_agent_mcp_namespace_is_policy_only():
    s = AgentFile(name="t", version=1, models=default_models())

    assert s.mcp.enabled is True
    assert not hasattr(s.mcp, "servers")


def test_agent_rejects_mcp_policy_server_definitions():
    with pytest.raises(Exception, match="servers"):
        AgentFile(
            name="t",
            version=1,
            models=default_models(),
            mcp={
                "servers": [
                    {
                        "id": "github",
                        "url": "http://mcp.example.com",
                    }
                ]
            },
        )


def test_alembic_ini_uses_default_fleetent_database_url():
    alembic_ini = (Path(__file__).parents[2] / "alembic.ini").read_text()

    assert "sqlalchemy.url = sqlite:///data/fleetent.db" in alembic_ini
    assert "sqlalchemy.url = sqlite:///data/users.db" not in alembic_ini


def test_settings_missing_yaml_file_uses_typed_defaults(tmp_path, monkeypatch):
    import fleetent.config as cfg

    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", tmp_path / "missing.yaml")

    s = Settings()

    assert s.database_url == f"sqlite:///{paths.data_dir() / 'fleetent.db'}"
    assert s.log_format == "console"


def test_settings_yaml_ignores_unknown_secret_like_keys(tmp_path, monkeypatch):
    # The slim platform Settings has no secret fields, so stray secret-like keys in
    # settings.yaml are simply ignored (extra="ignore"); non-secret values still load.
    import fleetent.config as cfg

    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text(
        "\n".join(
            [
                "anthropic_api_key: should-not-load",
                "slack_bot_token: xoxb-should-not-load",
                "database_url: sqlite:///tmp/fleetent.db",
            ]
        )
    )
    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", settings_yaml)
    monkeypatch.chdir(tmp_path)

    s = Settings()

    assert s.database_url == "sqlite:///tmp/fleetent.db"
    assert not hasattr(s, "anthropic_api_key")
    assert not hasattr(s, "slack_bot_token")


def test_observability_logging_defaults():
    s = Settings()

    assert s.observability.logging.console_level == "info"
    assert s.observability.logging.file_level == "debug"
    assert s.observability.logging.directory == str(paths.data_dir() / "logs")


def test_vector_store_defaults():
    s = AgentFile(name="t", version=1, models=default_models())

    assert s.vector_store.backend == "memory"
    assert s.vector_store.database_url is None
    assert s.embedding.backend == "deterministic"
    assert s.embedding.dimensions == 64
    assert s.embedding.endpoint == ""
    assert s.embedding.model == ""
    assert s.embedding.api_key_env == ""
    assert s.embedding.timeout_seconds == 10.0


def test_rerank_defaults():
    s = AgentFile(name="t", version=1, models=default_models())

    assert s.rerank.backend == "disabled"
    assert s.rerank.endpoint == ""
    assert s.rerank.model == ""
    assert s.rerank.api_key_env == ""
    assert s.rerank.timeout_seconds == 10.0


def test_knowledge_base_defaults():
    s = AgentFile(name="t", version=1, models=default_models())

    assert s.knowledge_base.enabled is False
    assert s.knowledge_base.default_tenant_id == "default"
    assert s.knowledge_base.default_kb_id == "global"
    assert s.knowledge_base.chunk_size > 0
    assert s.knowledge_base.chunk_overlap >= 0
    assert s.knowledge_base.chunk_overlap < s.knowledge_base.chunk_size


def test_diagnostics_defaults_are_conservative():
    s = AgentFile(name="t", version=1, models=default_models())

    assert s.diagnostics.export_dir == str(paths.data_dir() / "diagnostics")
    assert s.diagnostics.retention.enabled is False
    assert s.diagnostics.retention.logs_days is None
    assert s.diagnostics.retention.traces_days is None
    assert s.diagnostics.retention.diagnostic_exports_days is None


def test_diagnostics_retention_days_are_opt_in():
    s = AgentFile(
        name="t",
        version=1,
        models=default_models(),
        diagnostics={"retention": {"enabled": True, "logs_days": 7}},
    )

    assert s.diagnostics.retention.enabled is True
    assert s.diagnostics.retention.logs_days == 7
    assert s.diagnostics.retention.traces_days is None
    assert s.diagnostics.retention.diagnostic_exports_days is None


def test_vector_store_accepts_sqlite_backend_with_optional_database_url():
    s = AgentFile(
        name="t",
        version=1,
        models=default_models(),
        vector_store={"backend": "sqlite", "database_url": "sqlite:///tmp/vector.db"},
    )

    assert s.vector_store.backend == "sqlite"
    assert s.vector_store.database_url == "sqlite:///tmp/vector.db"


def test_sqlite_vector_backend_uses_global_database_url_when_not_configured(tmp_path):
    from fleetent.intelligence.vector_store.backend import (
        SQLiteVectorBackend,
        create_vector_backend,
    )

    # vector_store config now lives on the agent; the DB url falls back to the
    # platform Settings.database_url when the agent's vector_store has none.
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    platform = Settings(database_url=database_url)
    agent = AgentFile(
        name="t", version=1, models=default_models(), vector_store={"backend": "sqlite"}
    )

    backend = create_vector_backend(
        agent.vector_store,
        database_url=agent.vector_store.database_url or platform.database_url,
    )

    assert isinstance(backend, SQLiteVectorBackend)
    assert backend.database_url == database_url


def test_sqlite_vector_backend_rejects_non_sqlite_database_url():
    from fleetent.config import VectorStoreSettings
    from fleetent.intelligence.vector_store.backend import create_vector_backend

    with pytest.raises(ValueError, match="local sqlite database_url"):
        create_vector_backend(
            VectorStoreSettings(backend="sqlite", database_url="postgresql://db/app"),
            database_url="postgresql://db/app",
        )


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "json")
    s = Settings()
    assert s.log_format == "json"


def test_settings_needs_no_required_key(monkeypatch, tmp_path):
    # The platform Settings carries no required secret; it builds with no env/.env.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert s.database_url


def test_configure_logging_does_not_raise():
    s = Settings()
    configure_logging(s)  # should not raise
