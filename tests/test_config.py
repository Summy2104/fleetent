import pytest

from mini_agent.config import Settings, configure_logging


def test_settings_defaults():
    s = Settings(anthropic_api_key="test-key")
    assert s.microsandbox_url == "http://host.docker.internal:7777"
    assert s.permission_gate_medium_timeout_seconds == 300
    assert s.permission_gate_high_timeout_seconds == 3600


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("MICROSANDBOX_URL", "http://localhost:9999")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    s = Settings()
    assert s.microsandbox_url == "http://localhost:9999"


def test_settings_missing_required_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(Exception):  # noqa: B017
        Settings()  # no anthropic_api_key, no env var


def test_configure_logging_does_not_raise(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    s = Settings()
    configure_logging(s)  # should not raise
