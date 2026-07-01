"""FastAPI router for /admin/mcp.

Owns the MCP management behaviour only: server connection state, live tool listings,
reconnect, doctor, and stored server CRUD. Tool OAuth vault endpoints were retired.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from fleetent import audit_log, auth, user_store
from fleetent.platform.agent_lifecycle.materialize import mcp_yaml_field_paths
from fleetent.platform.connector_management import mcp_server_store
from fleetent.platform.connector_management.mcp_auth import (
    ApiKeyMcpAuthConfig,
    ApiKeyPerUserMcpAuthConfig,
    OAuthAuthorizationCodeMcpAuthConfig,
    OAuthClientCredentialsMcpAuthConfig,
    parse_mcp_auth_config,
)

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}
_SENSITIVE = ("secret", "token", "refresh", "api_key", "password")


def _normalized_auth_config(auth_type: str, auth_config: dict[str, Any]) -> dict[str, Any]:
    parsed = parse_mcp_auth_config(auth_type, auth_config)
    if isinstance(parsed, ApiKeyMcpAuthConfig):
        return {"key_env": parsed.key_env}
    if isinstance(parsed, OAuthClientCredentialsMcpAuthConfig):
        return {
            "token_url": parsed.token_url,
            "client_id": parsed.client_id,
            "client_secret_env": parsed.client_secret_env,
            "scope": parsed.scope,
        }
    if isinstance(parsed, OAuthAuthorizationCodeMcpAuthConfig):
        # per-user OAuth 2.1 authorization_code: structured non-secret fields + the
        # client_secret env reference (optional for PKCE public clients). Secret value never here.
        # token_env: which env var the per-user access token is injected under for a stdio
        # per-user OAuth subprocess (empty -> runtime default MCP_OAUTH_ACCESS_TOKEN).
        return {
            "authorization_endpoint": parsed.authorization_endpoint,
            "token_url": parsed.token_url,
            "client_id": parsed.client_id,
            "client_secret_env": parsed.client_secret_env,
            "scope": parsed.scope,
            "redirect_path": parsed.redirect_path,
            "token_env": parsed.token_env,
        }
    if isinstance(parsed, ApiKeyPerUserMcpAuthConfig):
        # per-user dynamic api-key/bearer: server-level method settings only (no static key).
        return {
            "header_style": parsed.header_style,
            "credential_input": parsed.credential_input,
        }
    return {}


class McpServerCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    agent_id: int | None = None
    transport: str = "stdio"
    url: str = ""
    auth_type: str = "none"
    auth_config: dict[str, Any] = Field(default_factory=dict)
    command: str = ""
    args: list[str] | None = None
    env: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_auth(self) -> McpServerCreateBody:
        self.auth_config = _normalized_auth_config(self.auth_type, self.auth_config)
        return self


class McpServerEditBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: str | None = None
    url: str | None = None
    auth_type: str | None = None
    auth_config: dict[str, Any] | None = None
    command: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    headers: dict[str, str] | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def _validate_auth(self) -> McpServerEditBody:
        if self.auth_type is None and self.auth_config is None:
            return self
        if self.auth_type is None or self.auth_config is None:
            raise ValueError("auth_type and auth_config must be updated together")
        self.auth_config = _normalized_auth_config(self.auth_type, self.auth_config)
        return self


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


def _validate_body[T: BaseModel](model: type[T], body: T | dict[str, Any]) -> T:
    if isinstance(body, BaseModel):
        return body
    try:
        return model.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=jsonable_encoder(exc.errors())) from exc


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


@router.get("/mcp/field-schema")
def mcp_field_schema_view(authorization: str | None = Header(None)) -> dict[str, str]:
    """Field name -> agent.yaml path template, for the admin form's per-field hints."""
    _current_user(authorization)
    return mcp_yaml_field_paths()


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
            "auth_type": row.get("auth_type") or "none",
            "auth_config": row.get("auth_config") or {},
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
    body: McpServerEditBody | dict[str, Any],
    authorization: str | None = Header(None),
    agent_id: int | None = None,
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if mcp_server_store.get_mcp_server(agent_id, server_id) is None:
        raise HTTPException(status_code=404, detail="mcp server not found")
    payload = _validate_body(McpServerEditBody, body).model_dump(exclude_none=True)
    mcp_server_store.edit_mcp_server(agent_id, server_id, **payload)
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
    server: McpServerCreateBody | dict[str, Any], authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    payload = _validate_body(McpServerCreateBody, server)

    server_id = payload.id
    agent_id = payload.agent_id
    if mcp_server_store.get_mcp_server(agent_id, server_id) is not None:
        raise HTTPException(status_code=409, detail="mcp server id already exists")

    mcp_server_store.add_mcp_server(
        agent_id=agent_id,
        server_id=server_id,
        transport=payload.transport,
        url=payload.url,
        auth_type=payload.auth_type,
        auth_config=payload.auth_config,
        command=payload.command,
        args=payload.args,
        env=payload.env,
        headers=payload.headers,
        enabled=payload.enabled,
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
