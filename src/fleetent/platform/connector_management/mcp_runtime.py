"""Bridge persisted MCP server definitions into the live MCP client.

Only global (``agent_id IS NULL``), enabled definitions from ``mcp_server_store``
are registered into the runtime so their tools become visible to agents; disabled or
deleted definitions are unregistered. Per-agent scoped registration is out of scope
here — this is the DB-authored global layer.
"""

from typing import Any

from fleetent.integrations.mcp import (
    McpServerConfig,
    probe_server,
    register_all,
    unregister_server,
)
from fleetent.platform.connector_management import mcp_server_store
from fleetent.platform.connector_management.mcp_auth import (
    ApiKeyMcpAuthConfig,
    OAuthClientCredentialsMcpAuthConfig,
    parse_mcp_auth_config,
)


def _row_to_config(row: dict[str, Any]) -> McpServerConfig:
    raw_auth_config = row.get("auth_config")
    if raw_auth_config is None and row.get("api_key_env"):
        raw_auth_config = {"key_env": row["api_key_env"]}
    auth_config = parse_mcp_auth_config(row.get("auth_type"), raw_auth_config)
    api_key_env = ""
    token_url = ""
    client_id = ""
    client_secret_env = ""
    scope = ""
    auth_type = row.get("auth_type") or "none"
    if isinstance(auth_config, ApiKeyMcpAuthConfig):
        auth_type = "api_key"
        api_key_env = auth_config.key_env
    elif isinstance(auth_config, OAuthClientCredentialsMcpAuthConfig):
        auth_type = "oauth2"
        token_url = auth_config.token_url
        client_id = auth_config.client_id
        client_secret_env = auth_config.client_secret_env
        scope = auth_config.scope
    return McpServerConfig(
        id=row["server_id"],
        transport=row["transport"] or "http",
        url=row.get("url") or "",
        auth_type=auth_type,
        api_key_env=api_key_env,
        token_url=token_url,
        client_id=client_id,
        client_secret_env=client_secret_env,
        scope=scope,
        command=row.get("command") or "",
        args=list(row.get("args") or []),
        env=dict(row.get("env") or {}),
        headers=dict(row.get("headers") or {}),
    )


def enabled_global_configs() -> list[McpServerConfig]:
    return [_row_to_config(r) for r in mcp_server_store.list_mcp_servers(None) if r["enabled"]]


async def register_global_store_servers() -> None:
    """Register all enabled global store servers at startup (best-effort connect)."""
    configs = enabled_global_configs()
    if configs:
        await register_all(configs)


async def sync_server(server_id: str) -> None:
    """Re-sync one global server's runtime registration to its current stored state.

    Drops the old tool set first (idempotent), then re-registers when the row still
    exists and is enabled. Used after admin add/edit/delete/disable so the change takes
    effect without a restart. A connect failure is swallowed by ``register_all``.
    """
    row = mcp_server_store.get_mcp_server(None, server_id)
    unregister_server(server_id)
    if row is not None and row["enabled"]:
        await register_all([_row_to_config(row)])


async def probe_global_server(server_id: str) -> dict[str, Any]:
    """Real connectivity test for a stored global server (initialize + tools/list)."""
    row = mcp_server_store.get_mcp_server(None, server_id)
    if row is None:
        return {"connected": False, "error": "server not found"}
    return await probe_server(_row_to_config(row))
