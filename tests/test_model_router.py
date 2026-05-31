from unittest.mock import patch

import pytest
from openai import AsyncOpenAI, OpenAI

from fleetent.model_router import (
    ROUTES,
    RouteConfig,
    RouteOverride,
    _apply_override,
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


def test_routes_define_vision():
    # AR21: vision task_type maps to a vision-capable chat provider.
    assert "vision" in ROUTES
    assert ROUTES["vision"].model


# --- RouteOverride dataclass (MR1) ---


def test_route_override_all_fields_default_none():
    o = RouteOverride()
    assert o.model is None
    assert o.base_url is None
    assert o.max_tokens is None
    assert o.api_key_env is None
    assert o.fallbacks is None


def test_route_override_is_frozen():
    o = RouteOverride(model="m")
    with pytest.raises((AttributeError, TypeError)):
        o.model = "changed"  # type: ignore[misc]


# --- _apply_override field-level merge (MR1) ---


def _base_cfg(fallbacks: tuple[str, ...] = ()) -> RouteConfig:
    return RouteConfig(
        base_url="https://base.test/v1/",
        model="base-model",
        api_key_env="BASE_KEY",
        max_tokens=4096,
        fallbacks=fallbacks,
    )


def test_apply_override_none_returns_cfg_unchanged():
    cfg = _base_cfg()
    assert _apply_override(cfg, None) == cfg


def test_apply_override_only_model_replaces_model_only():
    cfg = _base_cfg()
    result = _apply_override(cfg, RouteOverride(model="haiku"))
    assert result.model == "haiku"
    assert result.base_url == cfg.base_url
    assert result.api_key_env == cfg.api_key_env
    assert result.max_tokens == cfg.max_tokens


def test_apply_override_model_and_base_url_replaces_both():
    cfg = _base_cfg()
    result = _apply_override(cfg, RouteOverride(model="haiku", base_url="https://other/v1/"))
    assert result.model == "haiku"
    assert result.base_url == "https://other/v1/"
    assert result.api_key_env == cfg.api_key_env


def test_apply_override_max_tokens_and_api_key_env():
    cfg = _base_cfg()
    result = _apply_override(cfg, RouteOverride(max_tokens=128, api_key_env="OTHER_KEY"))
    assert result.max_tokens == 128
    assert result.api_key_env == "OTHER_KEY"
    assert result.model == cfg.model


# --- override-model clears fallbacks (MR1, D3) ---


def test_apply_override_model_without_fallbacks_clears_fallbacks():
    cfg = _base_cfg(fallbacks=("fb-1", "fb-2"))
    result = _apply_override(cfg, RouteOverride(model="haiku"))
    assert result.fallbacks == ()


def test_apply_override_explicit_fallbacks_wins():
    cfg = _base_cfg(fallbacks=("fb-1",))
    result = _apply_override(cfg, RouteOverride(model="haiku", fallbacks=("alt-1", "alt-2")))
    assert result.fallbacks == ("alt-1", "alt-2")


def test_apply_override_none_keeps_fallbacks():
    cfg = _base_cfg(fallbacks=("fb-1", "fb-2"))
    assert _apply_override(cfg, None).fallbacks == ("fb-1", "fb-2")


def test_apply_override_fallbacks_only_without_model():
    # Setting fallbacks but not model: fallbacks replaced, model unchanged.
    cfg = _base_cfg(fallbacks=("fb-1",))
    result = _apply_override(cfg, RouteOverride(fallbacks=("alt-1",)))
    assert result.model == cfg.model
    assert result.fallbacks == ("alt-1",)


# --- router entry points accept override (MR1) ---


def test_get_async_client_and_config_with_override_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _, cfg = get_async_client_and_config("default", override=RouteOverride(model="haiku"))
    assert cfg.model == "haiku"
    assert cfg.base_url == ROUTES["default"].base_url


def test_get_async_client_and_config_override_base_url_used_in_client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("fleetent.model_router.AsyncOpenAI") as mk:
        get_async_client_and_config(
            "default", override=RouteOverride(model="haiku", base_url="https://other/v1/")
        )
    assert mk.call_args.kwargs["base_url"] == "https://other/v1/"


def test_get_client_and_config_with_override_model(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _, cfg = get_client_and_config("default", override=RouteOverride(model="haiku"))
    assert cfg.model == "haiku"
    assert cfg.base_url == ROUTES["default"].base_url


def test_get_client_and_config_override_base_url_used_in_client(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    with patch("fleetent.model_router.OpenAI") as mk:
        get_client_and_config(
            "default", override=RouteOverride(model="haiku", base_url="https://other/v1/")
        )
    assert mk.call_args.kwargs["base_url"] == "https://other/v1/"


def test_override_none_is_byte_identical_routing(monkeypatch):
    # Regression guard: override=None must yield exactly the task_type route result.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _, cfg_no = get_async_client_and_config("default")
    _, cfg_none = get_async_client_and_config("default", override=None)
    assert cfg_none == cfg_no == ROUTES["default"]
    assert cfg_none.model == ROUTES["default"].model
    assert cfg_none.base_url == ROUTES["default"].base_url
    assert cfg_none.fallbacks == ROUTES["default"].fallbacks


# --- RouteConfig.params (task_type default sampling params) ---


def test_route_config_params_default_empty():
    cfg = RouteConfig(base_url="https://api.test.com", model="m", api_key_env="K", max_tokens=512)
    assert cfg.params == {}


def test_route_config_params_explicit():
    cfg = RouteConfig(
        base_url="https://api.test.com",
        model="m",
        api_key_env="K",
        max_tokens=512,
        params={"temperature": 0.0, "top_p": 0.9},
    )
    assert cfg.params == {"temperature": 0.0, "top_p": 0.9}


def test_route_config_params_independent_instances():
    # default_factory must give each instance its own dict, not a shared one.
    a = RouteConfig(base_url="b", model="m", api_key_env="K", max_tokens=1)
    b = RouteConfig(base_url="b", model="m", api_key_env="K", max_tokens=1)
    a.params["temperature"] = 0.5
    assert b.params == {}


# --- RouteOverride.params ---


def test_route_override_params_default_none():
    assert RouteOverride().params is None


def test_route_override_params_frozen():
    o = RouteOverride(params={"temperature": 0.0})
    with pytest.raises((AttributeError, TypeError)):
        o.params = {}  # type: ignore[misc]


# --- _apply_override params deep merge ---


def test_apply_override_params_overrides_key_keeps_others():
    cfg = RouteConfig(
        base_url="b",
        model="m",
        api_key_env="K",
        max_tokens=1,
        params={"temperature": 0.7, "top_p": 0.9},
    )
    result = _apply_override(cfg, RouteOverride(params={"temperature": 0.0}))
    assert result.params == {"temperature": 0.0, "top_p": 0.9}


def test_apply_override_params_adds_new_key():
    cfg = RouteConfig(
        base_url="b", model="m", api_key_env="K", max_tokens=1, params={"temperature": 0.7}
    )
    result = _apply_override(cfg, RouteOverride(params={"top_p": 0.5}))
    assert result.params == {"temperature": 0.7, "top_p": 0.5}


def test_apply_override_params_none_keeps_base_params():
    cfg = RouteConfig(
        base_url="b", model="m", api_key_env="K", max_tokens=1, params={"temperature": 0.7}
    )
    result = _apply_override(cfg, RouteOverride(model="other"))
    assert result.params == {"temperature": 0.7}


def test_apply_override_empty_params_keeps_base_params():
    cfg = RouteConfig(
        base_url="b", model="m", api_key_env="K", max_tokens=1, params={"temperature": 0.7}
    )
    result = _apply_override(cfg, RouteOverride(params={}))
    assert result.params == {"temperature": 0.7}


def test_apply_override_params_does_not_mutate_base():
    cfg = RouteConfig(
        base_url="b", model="m", api_key_env="K", max_tokens=1, params={"temperature": 0.7}
    )
    _apply_override(cfg, RouteOverride(params={"temperature": 0.0}))
    assert cfg.params == {"temperature": 0.7}


# --- D3 guard: built-in ROUTES params must not carry max_tokens ---


def test_builtin_routes_params_exclude_reserved_keys():
    reserved = {"max_tokens", "model", "messages", "tools"}
    for name, cfg in ROUTES.items():
        assert not (set(cfg.params) & reserved), f"route '{name}' params has reserved key"


def test_apply_override_strips_reserved_keys_from_params():
    # Guard D3: a reserved key in override.params would collide with the
    # explicit create() kwargs (duplicate kwarg TypeError); it must be dropped.
    cfg = RouteConfig(base_url="b", model="m", api_key_env="K", max_tokens=512)
    result = _apply_override(
        cfg, RouteOverride(params={"max_tokens": 99, "model": "x", "temperature": 0.5})
    )
    assert result.params == {"temperature": 0.5}


# --- end-to-end priority: override params > task_type params > provider default ---


def test_get_async_client_and_config_params_deep_merge(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setitem(
        ROUTES,
        "default",
        RouteConfig(
            base_url="https://api.anthropic.com/v1/",
            model="claude-sonnet-4-5",
            api_key_env="ANTHROPIC_API_KEY",
            max_tokens=4096,
            params={"temperature": 0.7, "top_p": 0.9},
        ),
    )
    _, cfg = get_async_client_and_config(
        "default", override=RouteOverride(params={"temperature": 0.0})
    )
    assert cfg.params == {"temperature": 0.0, "top_p": 0.9}


def test_get_async_client_and_config_no_override_uses_task_type_params(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setitem(
        ROUTES,
        "default",
        RouteConfig(
            base_url="https://api.anthropic.com/v1/",
            model="claude-sonnet-4-5",
            api_key_env="ANTHROPIC_API_KEY",
            max_tokens=4096,
            params={"temperature": 0.3},
        ),
    )
    _, cfg = get_async_client_and_config("default")
    assert cfg.params == {"temperature": 0.3}
