import pytest

from fleetent.config import Settings, configure_logging


def test_settings_defaults():
    s = Settings(anthropic_api_key="test-key")
    assert s.microsandbox_url == "http://host.docker.internal:7777"
    assert s.permission_gate_medium_timeout_seconds == 300
    assert s.permission_gate_high_timeout_seconds == 3600
    assert s.database_url == "sqlite:///data/users.db"


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
