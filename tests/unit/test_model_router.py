import pytest
from openai import AsyncOpenAI, OpenAI

from fleetent.model_router import (
    ROUTES,
    RouteConfig,
    get_async_client_and_config,
    get_client_and_config,
)


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


# --- fallbacks ---


def test_route_config_fallbacks_default_empty():
    cfg = RouteConfig(base_url="https://api.test.com", model="m", api_key_env="K", max_tokens=512)
    assert cfg.fallbacks == ()


def test_route_config_fallbacks_explicit():
    cfg = RouteConfig(
        base_url="https://api.test.com",
        model="primary",
        api_key_env="K",
        max_tokens=512,
        fallbacks=("fb-1", "fb-2"),
    )
    assert cfg.fallbacks == ("fb-1", "fb-2")


def test_route_config_fallbacks_immutable():
    cfg = RouteConfig(base_url="https://api.test.com", model="m", api_key_env="K", max_tokens=512)
    with pytest.raises((AttributeError, TypeError)):
        cfg.fallbacks = ("x",)  # type: ignore[misc]


# --- per-call overrides (agent-resource-isolation) ---


def test_async_overrides_layer_on_matching_task_type(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _, cfg = get_async_client_and_config("default", overrides={"default": {"model": "gpt-4o-mini"}})
    assert cfg.model == "gpt-4o-mini"
    # other fields untouched
    assert cfg.base_url == ROUTES["default"].base_url
    assert cfg.max_tokens == ROUTES["default"].max_tokens
    # global ROUTES is not mutated
    assert ROUTES["default"].model == "claude-sonnet-4-5"


def test_async_overrides_ignored_for_other_task_type(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _, cfg = get_async_client_and_config(
        "memory_extraction", overrides={"default": {"model": "gpt-4o-mini"}}
    )
    assert cfg == ROUTES["memory_extraction"]


def test_sync_overrides_layer_on_matching_task_type(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _, cfg = get_client_and_config("default", overrides={"default": {"max_tokens": 99}})
    assert cfg.max_tokens == 99
    assert cfg.model == ROUTES["default"].model


def test_overrides_none_is_noop(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _, cfg = get_async_client_and_config("default", overrides=None)
    assert cfg == ROUTES["default"]
