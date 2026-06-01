from pathlib import Path

import pytest

from fleetent.config import Settings, configure_logging


@pytest.fixture(autouse=True)
def isolate_settings_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_settings_defaults():
    s = Settings(anthropic_api_key="test-key")
    assert s.microsandbox_url == "http://host.docker.internal:7777"
    assert s.permission_gate_medium_timeout_seconds == 300
    assert s.permission_gate_high_timeout_seconds == 3600
    assert s.database_url == "sqlite:///data/users.db"


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
                "vector_store:",
                "  backend: sqlite",
                "embedding:",
                "  dimensions: 128",
                "knowledge_base:",
                "  enabled: true",
            ]
        )
    )
    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", settings_yaml)

    s = Settings(anthropic_api_key="test-key")

    assert s.database_url == "sqlite:///tmp/fleetent.db"
    assert s.log_format == "json"
    assert s.observability.logging.console_level == "warning"
    assert s.vector_store.backend == "sqlite"
    assert s.embedding.dimensions == 128
    assert s.knowledge_base.enabled is True


def test_settings_mcp_namespace_is_global_policy_only():
    s = Settings(anthropic_api_key="test-key")

    assert s.mcp.enabled is True
    assert not hasattr(s.mcp, "servers")


def test_settings_rejects_mcp_server_definitions():
    with pytest.raises(Exception, match="servers"):
        Settings(
            anthropic_api_key="test-key",
            mcp={
                "servers": [
                    {
                        "id": "github",
                        "url": "http://mcp.example.com",
                    }
                ]
            },
        )


def test_settings_example_excludes_mcp_server_definitions():
    example = (Path(__file__).parents[2] / "config" / "settings.yaml.example").read_text()

    assert "mcp:" in example
    assert "servers:" not in example
    assert "mcp-github" not in example


def test_mcp_servers_example_documents_server_list_format():
    example = (Path(__file__).parents[2] / "config" / "mcp.servers.yaml.example").read_text()

    assert "servers:" in example
    assert "id: github" in example
    assert "transport: http" in example
    assert "transport: stdio" in example


def test_settings_env_overrides_settings_yaml(tmp_path, monkeypatch):
    import fleetent.config as cfg

    settings_yaml = tmp_path / "settings.yaml"
    settings_yaml.write_text(
        "\n".join(
            [
                "database_url: sqlite:///tmp/from-yaml.db",
                "log_format: json",
            ]
        )
    )
    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", settings_yaml)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/from-env.db")

    s = Settings()

    assert s.database_url == "sqlite:///tmp/from-env.db"
    assert s.log_format == "json"


def test_settings_missing_yaml_file_uses_typed_defaults(tmp_path, monkeypatch):
    import fleetent.config as cfg

    monkeypatch.setattr(cfg, "SETTINGS_YAML_PATH", tmp_path / "missing.yaml")

    s = Settings(anthropic_api_key="test-key")

    assert s.database_url == "sqlite:///data/users.db"
    assert s.log_format == "console"


def test_settings_yaml_does_not_load_secret_values(tmp_path, monkeypatch):
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
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-env")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="anthropic_api_key.*slack_bot_token.*env/.env"):
        Settings()


def test_observability_logging_defaults():
    s = Settings(anthropic_api_key="test-key")

    assert s.observability.logging.console_level == "info"
    assert s.observability.logging.file_level == "debug"
    assert s.observability.logging.directory == "data/logs"


def test_vector_store_defaults():
    s = Settings(anthropic_api_key="test-key")

    assert s.vector_store.backend == "memory"
    assert s.vector_store.database_url is None
    assert s.embedding.backend == "deterministic"
    assert s.embedding.dimensions == 64
    assert s.embedding.endpoint == ""
    assert s.embedding.model == ""
    assert s.embedding.api_key_env == ""
    assert s.embedding.timeout_seconds == 10.0


def test_rerank_defaults():
    s = Settings(anthropic_api_key="test-key")

    assert s.rerank.backend == "disabled"
    assert s.rerank.endpoint == ""
    assert s.rerank.model == ""
    assert s.rerank.api_key_env == ""
    assert s.rerank.timeout_seconds == 10.0


def test_knowledge_base_defaults():
    s = Settings(anthropic_api_key="test-key")

    assert s.knowledge_base.enabled is False
    assert s.knowledge_base.default_tenant_id == "default"
    assert s.knowledge_base.default_kb_id == "global"
    assert s.knowledge_base.chunk_size > 0
    assert s.knowledge_base.chunk_overlap >= 0
    assert s.knowledge_base.chunk_overlap < s.knowledge_base.chunk_size


def test_vector_store_accepts_sqlite_backend_with_optional_database_url():
    s = Settings(
        anthropic_api_key="test-key",
        vector_store={"backend": "sqlite", "database_url": "sqlite:///tmp/vector.db"},
    )

    assert s.vector_store.backend == "sqlite"
    assert s.vector_store.database_url == "sqlite:///tmp/vector.db"


def test_sqlite_vector_backend_uses_global_database_url_when_not_configured(tmp_path):
    from fleetent.intelligence.vector_store.backend import (
        SQLiteVectorBackend,
        create_vector_backend,
    )

    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    s = Settings(
        anthropic_api_key="test-key",
        database_url=database_url,
        vector_store={"backend": "sqlite"},
    )

    backend = create_vector_backend(
        s.vector_store,
        database_url=s.vector_store.database_url or s.database_url,
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
    monkeypatch.setenv("MICROSANDBOX_URL", "http://localhost:9999")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    s = Settings()
    assert s.microsandbox_url == "http://localhost:9999"


def test_settings_missing_required_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here — prevents pydantic-settings from loading it
    with pytest.raises(Exception):  # noqa: B017
        Settings()


def test_configure_logging_does_not_raise(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    s = Settings()
    configure_logging(s)  # should not raise


def test_default_agent_name_defaults_to_none():
    s = Settings(anthropic_api_key="test-key")
    assert s.default_agent_name is None


def test_default_agent_name_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DEFAULT_AGENT_NAME", "basic")
    s = Settings()
    assert s.default_agent_name == "basic"
