"""Startup diagnostics emitted through structured logs."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Protocol

from fleetent.db import create_database
from fleetent.observability import get_logger


class ProviderKeyRoute(Protocol):
    api_key_env: str


def log_config_loaded() -> None:
    """Record successful configuration loading during startup."""
    get_logger("config").info("config loaded")


def log_config_failed(exception: BaseException) -> None:
    """Record configuration loading failure during startup."""
    get_logger("config").fatal(
        "config load failed",
        reason=str(exception),
        suggestion="Check .env and required settings before restarting.",
        exception=exception,
    )


def diagnose_database_writable(database_url: str) -> bool:
    """Check database writability and log a startup diagnostic on failure."""
    try:
        create_database(database_url).execute("PRAGMA user_version")
    except Exception as exc:
        get_logger("database").fatal(
            "database path is not writable",
            database_url=database_url,
            reason=str(exc),
            suggestion="Check database directory permissions and available disk space.",
            exception=exc,
        )
        return False
    get_logger("database").info("database writable", database_url=database_url)
    return True


def diagnose_provider_keys(routes: Iterable[ProviderKeyRoute]) -> None:
    """Warn for missing provider API keys discovered during startup."""
    seen: set[str] = set()
    for route in routes:
        if route.api_key_env in seen:
            continue
        seen.add(route.api_key_env)
        if not os.environ.get(route.api_key_env):
            get_logger("config").warn(
                "provider api key missing",
                api_key_env=route.api_key_env,
                reason=f"Missing environment variable {route.api_key_env}.",
                suggestion="Set the provider API key environment variable before using this route.",
            )


def log_mcp_server_unreachable(server_id: str, reason: str) -> None:
    """Record an optional MCP server startup degradation."""
    get_logger("mcp").warn(
        "mcp server unavailable",
        server_id=server_id,
        reason=reason,
        suggestion="Check MCP server configuration, network reachability, and credentials.",
    )
