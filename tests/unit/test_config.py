import pytest

from fleetent.config import Settings, configure_logging


def test_settings_defaults():
    s = Settings(anthropic_api_key="test-key")
    assert s.microsandbox_url == "http://host.docker.internal:7777"
    assert s.permission_gate_medium_timeout_seconds == 300
    assert s.permission_gate_high_timeout_seconds == 3600
    assert s.database_url == "sqlite:///data/users.db"


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
