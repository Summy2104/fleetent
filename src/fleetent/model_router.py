"""Route task types to OpenAI-compatible endpoints.

This module is intentionally a thin factory. It does not call any LLM,
maintains no state, and knows nothing about agents, tools, or memory.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
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
    params = cfg.params if override.params is None else {**cfg.params, **override.params}
    # A reserved key in params would collide with the explicit create() kwargs.
    # Fail loud rather than silently dropping it, so a config mistake surfaces
    # instead of the key being quietly ignored.
    reserved = set(params) & _RESERVED_PARAM_KEYS
    if reserved:
        raise ValueError(
            f"params must not contain reserved key(s) {sorted(reserved)}; "
            "these are controlled by the route config, not params"
        )
    return RouteConfig(
        base_url=override.base_url if override.base_url is not None else cfg.base_url,
        model=override.model if override.model is not None else cfg.model,
        api_key_env=override.api_key_env if override.api_key_env is not None else cfg.api_key_env,
        max_tokens=override.max_tokens if override.max_tokens is not None else cfg.max_tokens,
        fallbacks=fallbacks,
        params=params,
    )


# Built-in fallback route table. Used as-is when no routes file exists (open
# out of the box), and as the merge base when a file is present (file keys
# override same-named built-ins; uncovered built-in keys are preserved).
DEFAULT_ROUTES: dict[str, RouteConfig] = {
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

# Deployment-level routes file. Injectable module-level constant (no global
# mutable state): tests monkeypatch this to an isolated tmp path. Missing file
# is a normal state (built-in defaults are used); no hot reload.
ROUTES_PATH: Path = Path("config/routes.yaml")

# In-memory effective table; the merge base for _load_routes(). Tests that
# mutate routing (monkeypatch.setitem) operate on this.
ROUTES: dict[str, RouteConfig] = dict(DEFAULT_ROUTES)

# Allowed YAML keys per route. api_key is intentionally absent: keys are never
# inlined, only referenced by env var name (api_key_env).
_ALLOWED_ROUTE_KEYS = frozenset(
    {"base_url", "model", "api_key_env", "max_tokens", "fallbacks", "params"}
)


def _build_route(name: str, raw: Any) -> RouteConfig:
    """Construct a RouteConfig from one YAML route entry, failing loud on misuse."""
    if not isinstance(raw, dict):
        raise ValueError(f"route '{name}' in {ROUTES_PATH}: expected a mapping, got {type(raw)}")
    extra = set(raw) - _ALLOWED_ROUTE_KEYS
    if extra:
        raise ValueError(
            f"route '{name}' in {ROUTES_PATH}: unknown field(s) {sorted(extra)}; "
            "keys are referenced via api_key_env, never inlined"
        )
    for required in ("base_url", "model", "api_key_env", "max_tokens"):
        if required not in raw:
            raise ValueError(
                f"route '{name}' in {ROUTES_PATH}: missing required field '{required}'"
            )
    if not isinstance(raw["base_url"], str):
        raise ValueError(f"route '{name}' in {ROUTES_PATH}: 'base_url' must be a string")
    if not isinstance(raw["model"], str):
        raise ValueError(f"route '{name}' in {ROUTES_PATH}: 'model' must be a string")
    if not isinstance(raw["api_key_env"], str):
        raise ValueError(f"route '{name}' in {ROUTES_PATH}: 'api_key_env' must be a string")
    if not isinstance(raw["max_tokens"], int) or isinstance(raw["max_tokens"], bool):
        raise ValueError(f"route '{name}' in {ROUTES_PATH}: 'max_tokens' must be an int")
    fallbacks_raw = raw.get("fallbacks", [])
    if not isinstance(fallbacks_raw, list) or not all(isinstance(f, str) for f in fallbacks_raw):
        raise ValueError(f"route '{name}' in {ROUTES_PATH}: 'fallbacks' must be a list of strings")
    params = raw.get("params", {})
    if not isinstance(params, dict):
        raise ValueError(f"route '{name}' in {ROUTES_PATH}: 'params' must be a mapping")
    return RouteConfig(
        base_url=raw["base_url"],
        model=raw["model"],
        api_key_env=raw["api_key_env"],
        max_tokens=raw["max_tokens"],
        fallbacks=tuple(fallbacks_raw),
        params=dict(params),
    )


# Parsed-file cache keyed on (path, mtime, size). The expensive work (disk read +
# YAML parse + per-route validation) runs only when the file's path or contents
# change; the in-memory ROUTES merge below still runs every call so runtime edits
# stay visible. No hot reload / no background polling: the key is recomputed lazily
# on each call from a single stat().
_file_routes_cache: tuple[tuple[str, float, int], dict[str, RouteConfig]] | None = None


def _load_file_routes() -> dict[str, RouteConfig]:
    """Parse the routes file into RouteConfigs, cached by (path, mtime, size).

    Returns an empty mapping when the file is absent or empty. A present-but-corrupt
    file raises (fail loud). On the steady-state hot path (unchanged file) this skips
    the disk read, YAML parse, and validation entirely.
    """
    global _file_routes_cache
    if not ROUTES_PATH.exists():
        _file_routes_cache = None
        return {}
    stat = ROUTES_PATH.stat()
    key = (str(ROUTES_PATH), stat.st_mtime, stat.st_size)
    if _file_routes_cache is not None and _file_routes_cache[0] == key:
        return _file_routes_cache[1]
    try:
        raw = yaml.safe_load(ROUTES_PATH.read_text())
    except yaml.YAMLError as exc:
        raise ValueError(f"failed to parse routes file {ROUTES_PATH}: {exc}") from exc
    if raw is None:
        parsed: dict[str, RouteConfig] = {}
    elif not isinstance(raw, dict):
        raise ValueError(f"routes file {ROUTES_PATH}: top level must be a mapping, got {type(raw)}")
    else:
        parsed = {str(name): _build_route(str(name), entry) for name, entry in raw.items()}
    _file_routes_cache = (key, parsed)
    return parsed


def _load_routes() -> dict[str, RouteConfig]:
    """Resolve the effective route table: built-in defaults merged with the file.

    Missing file is normal (returns the in-memory defaults unchanged). A present
    but corrupt / malformed file fails loud rather than silently masking misconfig.
    The file parse is cached by (path, mtime, size); the in-memory ROUTES merge
    runs each call so runtime ROUTES edits stay visible.
    """
    base = dict(ROUTES)
    base.update(_load_file_routes())
    return base


def get_client_and_config(
    task_type: str = "default", override: RouteOverride | None = None
) -> tuple[OpenAI, RouteConfig]:
    """Return (OpenAI client, route config) for the given task type.

    An optional `override` is field-merged onto the task_type route result
    before the client is built (see `_apply_override`).
    """
    routes = _load_routes()
    cfg = _apply_override(routes.get(task_type, routes["default"]), override)
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
    routes = _load_routes()
    cfg = _apply_override(routes.get(task_type, routes["default"]), override)
    api_key = os.environ.get(cfg.api_key_env, "")
    return AsyncOpenAI(base_url=cfg.base_url, api_key=api_key), cfg
