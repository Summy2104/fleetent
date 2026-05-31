"""Route task types to OpenAI-compatible endpoints.

This module is intentionally a thin factory. It does not call any LLM,
maintains no state, and knows nothing about agents, tools, or memory.
"""

import os
from dataclasses import dataclass

from openai import AsyncOpenAI, OpenAI


@dataclass(frozen=True)
class RouteConfig:
    base_url: str
    model: str
    api_key_env: str
    max_tokens: int
    fallbacks: tuple[str, ...] = ()


@dataclass(frozen=True)
class RouteOverride:
    """Per-request routing override; all fields optional (None = inherit route)."""

    model: str | None = None
    base_url: str | None = None
    max_tokens: int | None = None
    api_key_env: str | None = None
    fallbacks: tuple[str, ...] | None = None


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
    return RouteConfig(
        base_url=override.base_url if override.base_url is not None else cfg.base_url,
        model=override.model if override.model is not None else cfg.model,
        api_key_env=override.api_key_env if override.api_key_env is not None else cfg.api_key_env,
        max_tokens=override.max_tokens if override.max_tokens is not None else cfg.max_tokens,
        fallbacks=fallbacks,
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
