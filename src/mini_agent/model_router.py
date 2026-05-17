"""Route task types to OpenAI-compatible endpoints.

This module is intentionally a thin factory. It does not call any LLM,
maintains no state, and knows nothing about agents, tools, or memory.
"""

import os
from dataclasses import dataclass

from openai import OpenAI


@dataclass(frozen=True)
class RouteConfig:
    base_url: str
    model: str
    api_key_env: str
    max_tokens: int


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


def get_client_and_config(task_type: str = "default") -> tuple[OpenAI, RouteConfig]:
    """Return (OpenAI client, route config) for the given task type."""
    route = ROUTES.get(task_type, ROUTES["default"])
    api_key = os.environ.get(route.api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing env var {route.api_key_env} for route '{task_type}'")
    client = OpenAI(base_url=route.base_url, api_key=api_key)
    return client, route
