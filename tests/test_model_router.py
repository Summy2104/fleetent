import pytest
from openai import AsyncOpenAI, OpenAI

from mini_agent.model_router import ROUTES, get_async_client_and_config, get_client_and_config


def test_routes_define_default_and_memory_extraction():
    assert "default" in ROUTES
    assert "memory_extraction" in ROUTES


def test_route_config_is_frozen():
    with pytest.raises((AttributeError, TypeError)):
        ROUTES["default"].model = "changed"  # type: ignore[misc]


def test_get_client_and_config_default(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client, cfg = get_client_and_config("default")
    assert isinstance(client, OpenAI)
    assert cfg.model == "claude-sonnet-4-5"
    assert cfg.max_tokens == 4096


def test_get_client_and_config_missing_key_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env to load from
    with pytest.raises(RuntimeError, match="Missing env var"):
        get_client_and_config("default")


def test_get_client_and_config_unknown_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _, cfg = get_client_and_config("nonexistent_route")
    assert cfg == ROUTES["default"]


def test_get_async_client_and_config_returns_async_client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client, cfg = get_async_client_and_config("default")
    assert isinstance(client, AsyncOpenAI)
    assert cfg.model == "claude-sonnet-4-5"


def test_get_async_client_and_config_memory_route(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _, cfg = get_async_client_and_config("memory_extraction")
    assert cfg.model == "claude-haiku-4-5"
    assert cfg.max_tokens == 1024
