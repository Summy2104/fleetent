"""Route task types to OpenAI-compatible endpoints.

This module is intentionally a thin factory. It does not call any LLM,
maintains no state, and knows nothing about agents, tools, or memory.
"""

import os
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI, OpenAI

# Reserved create() kwargs that params MUST NOT carry: they are passed as
# explicit keyword args, so a same-named key in params would raise a duplicate
# keyword TypeError (D3). Stripped during merge as a defensive guard.
_RESERVED_PARAM_KEYS = frozenset({"max_tokens", "model", "messages", "tools"})


@dataclass(frozen=True)
class RouteConfig:
    base_url: str
    model: str
    api_key_env: str
    max_tokens: int
    fallbacks: tuple[str, ...] = ()
    # Per task_type default sampling params (e.g. temperature/top_p), passed
    # through to create() as **params. MUST NOT contain max_tokens/model/
    # messages/tools (would collide with those explicit kwargs).
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouteOverride:
    """Per-request routing override; all fields optional (None = inherit route)."""

    model: str | None = None
    base_url: str | None = None
    max_tokens: int | None = None
    api_key_env: str | None = None
    fallbacks: tuple[str, ...] | None = None
    # Per-call sampling param override; deep-merged onto RouteConfig.params
    # (None = inherit the route's params unchanged).
    params: dict[str, Any] | None = None


def _apply_override(cfg: RouteConfig, override: RouteOverride | None) -> RouteConfig:
    """Field-level merge of an override onto a base route config.

    Non-None override fields replace the corresponding config field; None fields
    inherit the task_type route result. Forcing a model (override.model set)
    without explicit fallbacks clears the fallback chain (D3): a request-level
    override means "use this model now", not "fall back to the route's chain".
    """
    if override is None:
        return cfg
    fallbacks = cfg.fallbacks
    if override.fallbacks is not None:
        fallbacks = override.fallbacks
    elif override.model is not None:
        fallbacks = ()
    # Deep-merge params by key: override keys replace same-named base keys,
    # uncovered base keys carry over (D2). None override params inherit base.
    if override.params is None:
        params = cfg.params
    else:
        merged = {**cfg.params, **override.params}
        params = {k: v for k, v in merged.items() if k not in _RESERVED_PARAM_KEYS}
    return RouteConfig(
        base_url=override.base_url if override.base_url is not None else cfg.base_url,
        model=override.model if override.model is not None else cfg.model,
        api_key_env=override.api_key_env if override.api_key_env is not None else cfg.api_key_env,
        max_tokens=override.max_tokens if override.max_tokens is not None else cfg.max_tokens,
        fallbacks=fallbacks,
        params=params,
    )


ROUTES: dict[str, RouteConfig] = {
    "default": RouteConfig(
        base_url="https://api.anthropic.com/v1/",
        model="claude-sonnet-4-5",
        api_key_env="ANTHROPIC_API_KEY",
        max_tokens=4096,
    ),
    "memory_extraction": RouteConfig(
        base_url="https://api.anthropic.com/v1/",
        model="claude-haiku-4-5",
        api_key_env="ANTHROPIC_API_KEY",
        max_tokens=1024,
    ),
    # AR21: messages carrying image blocks route here. Maps to a vision-capable
    # chat provider; self-hostable backends can repoint base_url/model.
    "vision": RouteConfig(
        base_url="https://api.anthropic.com/v1/",
        model="claude-sonnet-4-5",
        api_key_env="ANTHROPIC_API_KEY",
        max_tokens=4096,
    ),
    # Acceptance: flip "default" base_url + model to a different provider
    # (e.g. self-hosted vLLM or OpenAI) and the rest of the system must
    # keep working unchanged.
}


def get_client_and_config(
    task_type: str = "default", override: RouteOverride | None = None
) -> tuple[OpenAI, RouteConfig]:
    """Return (OpenAI client, route config) for the given task type.

    An optional `override` is field-merged onto the task_type route result
    before the client is built (see `_apply_override`).
    """
    cfg = _apply_override(ROUTES.get(task_type, ROUTES["default"]), override)
    api_key = os.environ.get(cfg.api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing env var {cfg.api_key_env} for route '{task_type}'")
    client = OpenAI(base_url=cfg.base_url, api_key=api_key)
    return client, cfg


def get_async_client_and_config(
    task_type: str = "default", override: RouteOverride | None = None
) -> tuple[AsyncOpenAI, RouteConfig]:
    """Return an async OpenAI client and route config for the given task type.

    An optional `override` is field-merged onto the task_type route result
    before the client is built (see `_apply_override`).
    """
    cfg = _apply_override(ROUTES.get(task_type, ROUTES["default"]), override)
    api_key = os.environ.get(cfg.api_key_env, "")
    return AsyncOpenAI(base_url=cfg.base_url, api_key=api_key), cfg
