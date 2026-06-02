"""Route task types to OpenAI-compatible endpoints.

This module is intentionally a thin factory. It does not call any LLM,
maintains no state, and knows nothing about agents, tools, or memory.
"""

import os
from dataclasses import dataclass, replace
from typing import Any

from openai import AsyncOpenAI, OpenAI


@dataclass(frozen=True)
class RouteConfig:
    base_url: str
    model: str
    api_key_env: str
    max_tokens: int
    fallbacks: tuple[str, ...] = ()


def _resolve_route(task_type: str, overrides: dict[str, dict[str, Any]] | None) -> RouteConfig:
    """Pick the route for ``task_type`` and layer per-call overrides on top.

    Overrides let a single agent run with its own model config without mutating
    the global ``ROUTES`` table; only the requested task type's entry is applied.
    """
    route = ROUTES.get(task_type, ROUTES["default"])
    if overrides and task_type in overrides:
        route = replace(route, **overrides[task_type])
    return route


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
    # Acceptance: flip "default" base_url + model to a different provider
    # (e.g. self-hosted vLLM or OpenAI) and the rest of the system must
    # keep working unchanged.
}


def get_client_and_config(
    task_type: str = "default",
    overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[OpenAI, RouteConfig]:
    """Return (OpenAI client, route config) for the given task type."""
    route = _resolve_route(task_type, overrides)
    api_key = os.environ.get(route.api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing env var {route.api_key_env} for route '{task_type}'")
    client = OpenAI(base_url=route.base_url, api_key=api_key)
    return client, route


def get_async_client_and_config(
    task_type: str = "default",
    overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[AsyncOpenAI, RouteConfig]:
    """Return an async OpenAI client and route config for the given task type."""
    cfg = _resolve_route(task_type, overrides)
    api_key = os.environ.get(cfg.api_key_env, "")
    return AsyncOpenAI(base_url=cfg.base_url, api_key=api_key), cfg
