"""FastAPI router for /admin/mcp.

Owns the MCP management behaviour only: server connection state, live tool listings,
reconnect, doctor, and stored server CRUD. Tool OAuth vault endpoints were retired.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from fleetent import audit_log, auth, user_store
from fleetent.platform.connector_management import mcp_server_store

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}
_SENSITIVE = ("secret", "token", "refresh", "api_key", "password")


def mcp_list_servers() -> list[dict[str, Any]]:
    """MCP server connection states. Owned by mcp (placeholder)."""
    return []


def mcp_list_tools(server_id: str) -> list[dict[str, Any]]:
    """Tools registered by a server as ``server__{tool}`` with schema summary."""
    return []


def mcp_reconnect(server_id: str) -> dict[str, Any]:
    """Trigger a re-handshake for an MCP server. Owned by mcp (placeholder)."""
    return {"server_id": server_id, "reconnected": False, "wired": False}


def mcp_doctor() -> dict[str, Any]:
    """MCP environment health check (red/yellow/green). Owned by mcp (placeholder)."""
    return {"checks": []}


async def mcp_sync_server(server_id: str, agent_id: int | None) -> None:
    """Re-sync a global server's live runtime registration after a config change."""
    if agent_id is not None:
        return
    from fleetent.platform.connector_management import mcp_runtime

    await mcp_runtime.sync_server(server_id)


async def mcp_probe(server_id: str) -> dict[str, Any]:
    """Real connectivity test for a stored global server (initialize + tools/list)."""
    from fleetent.platform.connector_management import mcp_runtime

    return await mcp_runtime.probe_global_server(server_id)


def _mask(value: Any) -> Any:
    """Recursively mask sensitive values (secret/token/refresh/api_key/password)."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and any(s in k.lower() for s in _SENSITIVE) and v:
                out[k] = "****"
            else:
                out[k] = _mask(v)
        return out
    if isinstance(value, list):
        return [_mask(v) for v in value]
    return value


def _mask_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    """Mask a dict-or-None result, returning an empty dict when absent."""
    if value is None:
        return {}
    return _mask(value)


def _session_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    user_id = auth.validate_session(authorization.split(" ", 1)[1], IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


def _current_user(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, {"viewer", *_ADMIN_ROLES}):
        raise HTTPException(status_code=403, detail="forbidden")
    return user


def _require_admin(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


@router.get("/mcp/doctor")
def mcp_doctor_view(authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    return _mask_dict(mcp_doctor())


@router.get("/mcp/servers")
def list_mcp_servers(
    authorization: str | None = Header(None), agent_id: int | None = None
) -> list[dict[str, Any]]:
    _current_user(authorization)
    servers: list[dict[str, Any]] = [{**s, "agent_id": None} for s in mcp_list_servers()]
    seen = {s["id"] for s in servers}

    def _from_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["server_id"],
            "transport": row["transport"],
            "url": row["url"],
            "command": row["command"],
            "args": row["args"],
            "env": row["env"],
            "headers": row["headers"],
            "enabled": row["enabled"],
            "status": "configured" if row["enabled"] else "disabled",
            "tool_count": 0,
            "agent_id": row["agent_id"],
        }

    for row in mcp_server_store.list_mcp_servers(None):
        if row["server_id"] not in seen:
            servers.append(_from_row(row))
            seen.add(row["server_id"])
    if agent_id is not None:
        for row in mcp_server_store.list_mcp_servers(agent_id):
            servers.append(_from_row(row))
    return [_mask(s) for s in servers]


@router.get("/mcp/servers/{server_id}/tools")
async def list_mcp_tools(
    server_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    if mcp_server_store.get_mcp_server(None, server_id) is None:
        return {"connected": False, "error": "Server configuration not found", "tools": []}
    result = await mcp_probe(server_id)
    return {
        "connected": bool(result.get("connected")),
        "tools": result.get("tools", []),
        "error": result.get("error"),
    }


@router.post("/mcp/servers/{server_id}/reconnect")
def reconnect_mcp(server_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    result = mcp_reconnect(server_id)
    audit_log.write_audit(user.id, "mcp.reconnect", "mcp_server", server_id)
    return result


@router.put("/mcp/servers/{server_id}")
async def edit_mcp_server(
    server_id: str,
    body: dict[str, Any],
    authorization: str | None = Header(None),
    agent_id: int | None = None,
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if mcp_server_store.get_mcp_server(agent_id, server_id) is None:
        raise HTTPException(status_code=404, detail="mcp server not found")
    mcp_server_store.edit_mcp_server(agent_id, server_id, **body)
    audit_log.write_audit(user.id, "mcp.edit", "mcp_server", server_id)
    await mcp_sync_server(server_id, agent_id)
    return {"success": True, "server_id": server_id}


@router.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(
    server_id: str,
    authorization: str | None = Header(None),
    agent_id: int | None = None,
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if mcp_server_store.get_mcp_server(agent_id, server_id) is None:
        raise HTTPException(status_code=404, detail="mcp server not found")
    mcp_server_store.delete_mcp_server(agent_id, server_id)
    audit_log.write_audit(user.id, "mcp.delete", "mcp_server", server_id)
    await mcp_sync_server(server_id, agent_id)
    return {"success": True, "server_id": server_id}


@router.post("/mcp/servers")
async def create_mcp_server(
    server: dict[str, Any], authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)

    server_id = server.get("id") or server.get("server_id")
    if not isinstance(server_id, str) or not server_id:
        raise HTTPException(status_code=422, detail="server id is required")
    agent_id = server.get("agent_id")
    if mcp_server_store.get_mcp_server(agent_id, server_id) is not None:
        raise HTTPException(status_code=409, detail="mcp server id already exists")
    transport = server.get("transport", "stdio")

    mcp_server_store.add_mcp_server(
        agent_id=agent_id,
        server_id=server_id,
        transport=transport,
        url=server.get("url", ""),
        auth_type=server.get("auth_type", "none"),
        api_key_env=server.get("api_key_env", ""),
        command=server.get("command", ""),
        args=server.get("args"),
        env=server.get("env"),
        headers=server.get("headers"),
    )

    audit_log.write_audit(user.id, "mcp.create", "mcp_server", server_id)
    await mcp_sync_server(server_id, agent_id)
    return {"success": True, "server_id": server_id}


@router.post("/mcp/servers/{server_id}/test")
async def test_mcp_server(
    server_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    row = mcp_server_store.get_mcp_server(None, server_id)
    if row is None:
        return {
            "success": False,
            "server_id": server_id,
            "connected": False,
            "error": "Server configuration not found",
        }
    result = await mcp_probe(server_id)
    return {
        "success": bool(result.get("connected")),
        "server_id": server_id,
        "transport": row["transport"],
        "tools_count": result.get("tool_count", 0),
        **result,
    }
