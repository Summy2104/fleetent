"""FastAPI router for /admin/connectors and /admin/mcp — the connector management face.

Owns the management behaviour only: the OAuth connector config catalog (CRUD, secrets
masked), the per-user authorization-status matrix (with the "admin cannot complete
first consent" guard), admin-initiated revoke, offboarding-cascade visibility, and
the MCP server connection/tools/reconnect/doctor views.

OAuth consent/refresh/revoke semantics belong to the connectors engine domain; MCP
connection/registration/degradation belong to the mcp domain; tool access control
belongs to governance. Those are reached through injectable seams (mockable in tests).
Only the connector config catalog is persisted here. Secrets/tokens are never returned
plaintext — masking is applied in the serialization layer. Never imports the agent loop.
"""

import secrets
from typing import Any, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from fleetent import audit_log, auth, user_store
from fleetent.platform.connector_management import (
    agent_service_grant_store,
    external_credential_store,
    external_service_store,
    mcp_server_store,
    service_providers,
    vault_provider,
)

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin"}
_SENSITIVE = ("secret", "token", "refresh", "api_key", "password")
_pending_consent_states: dict[str, tuple[str, str]] = {}

# Maps external_credentials.status → matrix status name visible to callers.
# "error" → "credential_error" matches the four-state enum the matrix exposes.
_STATUS_MAP: dict[str, str] = {
    "authorized": "authorized",
    "needs_reauth": "needs_reauth",
    "error": "credential_error",
}


# --- connector admin seams (wired to Vault) -----------------------------------


def connectors_list_grants(agent_id: int | None = None) -> list[dict[str, Any]]:
    """(user, connector) authorization matrix derived from current Vault rows.

    Matrix is single-level global — the ``agent_id`` param is accepted for API
    compatibility but ignored (spec: no owning-agent dimension). Status values:
    authorized / needs_reauth / credential_error. Users with no row are absent
    (the caller infers not_authorized from absence).
    """
    del agent_id  # global-only per spec; kept for endpoint compat
    rows = external_credential_store.list_all_credentials()
    return [
        {
            "user_id": row["user_id"],
            "connector_id": row["service_id"],
            "status": _STATUS_MAP.get(row["status"], row["status"]),
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def connectors_revoke(user_id: str, connector_id: str) -> dict[str, Any]:
    """Revoke a user's connector credential via the Vault (delete local + OAuth revoke)."""
    result = vault_provider.revoke_credential(user_id, connector_id)
    return {"user_id": user_id, "connector_id": connector_id, **result}


def connectors_offboarding_result(user_id: str) -> dict[str, Any]:
    """Revoke all connector credentials for a user and report per-service success/failure.

    Idempotent: if credentials are already gone the service still appears in ``revoked``.
    """
    creds = external_credential_store.list_credentials_for_user(user_id)
    revoked: list[str] = []
    failed: list[str] = []
    for cred in creds:
        service_id = cred["service_id"]
        try:
            result = vault_provider.revoke_credential(user_id, service_id)
            if result.get("revoked"):
                revoked.append(service_id)
            else:
                failed.append(service_id)
        except Exception:
            failed.append(service_id)
    return {"user_id": user_id, "revoked": revoked, "failed": failed}


def connector_lifecycle_stats(connector_id: str) -> dict[str, Any]:
    """Refresh success/failure + re-auth counts derived from current credential statuses.

    No history table exists; stats are inferred from the live status column:
    authorized → refresh_ok, error → refresh_failed, needs_reauth → reauths.
    """
    counts = external_credential_store.count_credentials_by_status(connector_id)
    return {
        "connector_id": connector_id,
        "refresh_ok": counts.get("authorized", 0),
        "refresh_failed": counts.get("error", 0),
        "reauths": counts.get("needs_reauth", 0),
    }


def mcp_list_servers() -> list[dict[str, Any]]:
    """MCP server connection states. Owned by mcp (placeholder).

    Each: ``{id, transport, status, tool_count}`` status in
    connected / degraded / reconnecting / permanently_unavailable.
    """
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
    """Re-sync a global server's live runtime registration after a config change.

    Only the global layer (``agent_id is None``) is wired into the runtime; agent-scoped
    rows are skipped. An injectable seam so endpoint tests stay hermetic (no real network).
    """
    if agent_id is not None:
        return
    from fleetent.platform.connector_management import mcp_runtime

    await mcp_runtime.sync_server(server_id)


async def mcp_probe(server_id: str) -> dict[str, Any]:
    """Real connectivity test for a stored global server (initialize + tools/list)."""
    from fleetent.platform.connector_management import mcp_runtime

    return await mcp_runtime.probe_global_server(server_id)


# --- masking ------------------------------------------------------------------


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
    return cast(dict[str, Any], _mask(value))


# --- auth helpers -------------------------------------------------------------


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


def _require_confirm(x_confirm: str | None) -> None:
    if x_confirm != "true":
        raise HTTPException(status_code=428, detail="confirmation required for high-risk action")


# --- request bodies -----------------------------------------------------------


class ConnectorBody(BaseModel):
    id: str
    display_name: str
    protocol: str = "oauth2"
    oauth_config: dict[str, Any] | None = None
    enabled: bool = True


class ConnectorEditBody(BaseModel):
    display_name: str | None = None
    protocol: str | None = None
    oauth_config: dict[str, Any] | None = None
    enabled: bool | None = None


class ApiKeyBody(BaseModel):
    api_key: str


def _service_to_connector_payload(service: dict[str, Any]) -> dict[str, Any]:
    payload = dict(service)
    payload["id"] = payload["service_id"]
    return payload


def _service_oauth_config(service_id: str) -> dict[str, Any]:
    service = external_service_store.get_service(service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="connector not found")
    return service.get("oauth_config", {})


# --- OAuth connector catalog --------------------------------------------------


@router.get("/connectors/grants")
def authorization_matrix(
    authorization: str | None = Header(None), agent_id: int | None = None
) -> dict[str, Any]:
    _current_user(authorization)
    grants = _mask(connectors_list_grants(agent_id))
    # admin cannot complete a user's first consent — surface the hint, expose no route.
    return {
        "grants": grants,
        "consent_hint": "first consent must be completed by the user in their own browser; "
        "admin cannot authorize on their behalf",
    }


@router.get("/connectors/offboarding/{user_id}")
def offboarding_result(user_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    return _mask_dict(connectors_offboarding_result(user_id))


@router.get("/connectors")
def list_connectors(
    authorization: str | None = Header(None), agent_id: int | None = None
) -> list[dict[str, Any]]:
    _current_user(authorization)
    del agent_id
    return [
        _mask(_service_to_connector_payload(service))
        for service in external_service_store.list_services()
    ]


@router.get("/connectors/authorize/{service_id}")
def authorize_connector(
    service_id: str, request: Request, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _current_user(authorization)
    oauth_config = _service_oauth_config(service_id)
    authorize_url = oauth_config.get("authorize")
    client_id = oauth_config.get("client_id")
    if not authorize_url or not client_id:
        raise HTTPException(status_code=422, detail="connector authorize metadata missing")
    state = secrets.token_urlsafe(24)
    _pending_consent_states[state] = (user.id, service_id)
    scopes = oauth_config.get("scopes", [])
    redirect_uri = str(request.url_for("oauth_callback", service_id=service_id))
    provider = service_providers.get_provider(service_id)
    query = provider.build_authorize_params(client_id, redirect_uri, state, scopes)
    return {"authorize_url": f"{authorize_url}?{urlencode(query)}"}


@router.get("/connectors/callback/{service_id}", name="oauth_callback")
def oauth_callback(
    service_id: str,
    state: str,
    code: str,
    request: Request,
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    user = _current_user(authorization)
    pending = _pending_consent_states.pop(state, None)
    if pending != (user.id, service_id):
        raise HTTPException(status_code=400, detail="invalid consent state")
    oauth_config = _service_oauth_config(service_id)
    token_url = oauth_config.get("token")
    client_id = oauth_config.get("client_id")
    if not token_url or not client_id:
        raise HTTPException(status_code=422, detail="connector token metadata missing")
    provider = service_providers.get_provider(service_id)
    redirect_uri = str(request.url_for("oauth_callback", service_id=service_id))
    payload = provider.exchange_code(
        code,
        client_id,
        service_providers.client_secret_for(service_id),
        redirect_uri,
        token_url,
    )
    external_credential_store.put_oauth_credential(
        user.id,
        service_id,
        payload,
        updated_by=user.id,
        status="authorized",
    )
    return {"authorized": True, "service_id": service_id}


@router.post("/connectors/{service_id}/credentials")
def submit_api_key(
    service_id: str, body: ApiKeyBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    """User self-submits their own API key for an ``apikey``-protocol connector.

    The key is bound to the authenticated session's own user — there is no target
    ``user_id`` parameter, so an admin cannot fill a key on another user's behalf.
    The plaintext key is encrypted at rest and never echoed back.
    """
    user = _session_user(authorization)
    service = external_service_store.get_service(service_id)
    if service is None:
        raise HTTPException(status_code=404, detail="connector not found")
    if service.get("protocol") != "apikey":
        raise HTTPException(status_code=422, detail="connector does not use api-key auth")
    if not body.api_key:
        raise HTTPException(status_code=422, detail="api_key is required")
    external_credential_store.put_apikey_credential(
        user.id, service_id, body.api_key, updated_by=user.id
    )
    return {"submitted": True, "service_id": service_id}


@router.post("/connectors")
def add_connector(body: ConnectorBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if body.protocol not in {"oauth2", "apikey"}:
        raise HTTPException(status_code=422, detail="unsupported connector protocol")
    if external_service_store.get_service(body.id) is not None:
        raise HTTPException(status_code=409, detail="connector id already exists")
    external_service_store.add_service(
        body.id,
        body.display_name,
        oauth_config=body.oauth_config,
        protocol=body.protocol,
        enabled=body.enabled,
    )
    audit_log.write_audit(user.id, "connector.add", "connector", body.id)
    created = external_service_store.get_service(body.id)
    assert created is not None
    return _mask_dict(_service_to_connector_payload(created))


@router.put("/connectors/{connector_id}")
def edit_connector(
    connector_id: str, body: ConnectorEditBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if body.protocol is not None and body.protocol not in {"oauth2", "apikey"}:
        raise HTTPException(status_code=422, detail="unsupported connector protocol")
    if external_service_store.get_service(connector_id) is None:
        raise HTTPException(status_code=404, detail="connector not found")
    external_service_store.edit_service(connector_id, **body.model_dump(exclude_unset=True))
    audit_log.write_audit(user.id, "connector.edit", "connector", connector_id)
    updated = external_service_store.get_service(connector_id)
    assert updated is not None
    return _mask_dict(_service_to_connector_payload(updated))


@router.delete("/connectors/{connector_id}")
def delete_connector(connector_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if external_service_store.get_service(connector_id) is None:
        raise HTTPException(status_code=404, detail="connector not found")
    external_service_store.delete_service(connector_id)
    audit_log.write_audit(user.id, "connector.delete", "connector", connector_id)
    return {"success": True, "connector_id": connector_id}


@router.get("/connectors/{connector_id}/bindings/agents")
def list_connector_binding_agents(
    connector_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    _current_user(authorization)
    if external_service_store.get_service(connector_id) is None:
        raise HTTPException(status_code=404, detail="connector not found")
    return {
        "service_id": connector_id,
        "agent_ids": agent_service_grant_store.list_agents_for_service(connector_id),
    }


@router.get("/connectors/{connector_id}/lifecycle")
def lifecycle(connector_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    return connector_lifecycle_stats(connector_id)


@router.post("/connectors/{connector_id}/test")
def test_oauth_connector(
    connector_id: str, authorization: str | None = Header(None)
) -> dict[str, Any]:
    """Test OAuth connector by checking token validity and lifecycle."""
    _current_user(authorization)
    try:
        # Get connector config to check if it exists
        connector = external_service_store.get_service(connector_id)
        if not connector:
            return {"success": False, "connector_id": connector_id, "error": "Connector not found"}

        # Get lifecycle stats to check token validity
        stats = connector_lifecycle_stats(connector_id)

        # Check if there are any active tokens
        has_active_tokens = stats.get("active_grants", 0) > 0
        token_valid = has_active_tokens and stats.get("last_refresh_success", False)

        return {
            "success": True,
            "connector_id": connector_id,
            "enabled": connector.get("enabled", False),
            "token_valid": token_valid,
            "active_grants": stats.get("active_grants", 0),
            "last_refresh": stats.get("last_refresh_at"),
            "display_name": connector.get("display_name", connector_id),
        }
    except Exception as e:
        return {"success": False, "connector_id": connector_id, "error": str(e)}


@router.post("/connectors/grants/{user_id}/{connector_id}/revoke")
def revoke_grant(
    user_id: str,
    connector_id: str,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_confirm(x_confirm)
    result = connectors_revoke(user_id, connector_id)
    audit_log.write_audit(
        user.id, "connector.revoke", "connector", connector_id, detail={"target_user": user_id}
    )
    return _mask_dict(result)


# --- MCP servers --------------------------------------------------------------


@router.get("/mcp/doctor")
def mcp_doctor_view(authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    return _mask_dict(mcp_doctor())


@router.get("/mcp/servers")
def list_mcp_servers(
    authorization: str | None = Header(None), agent_id: int | None = None
) -> list[dict[str, Any]]:
    _current_user(authorization)
    # Runtime connection states are owned by the mcp domain (placeholder until wired).
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

    # Persisted definitions: global defaults always, plus the agent's own when scoped.
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
    """Live tool catalog for a stored MCP server (connects + tools/list).

    Returns ``{connected, tools: [{name, description}], error?}`` so the detail view
    can show what the server actually exposes, not a stored guess.
    """
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
    """Edit a stored MCP server definition. `enabled: false` deactivates it."""
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
    """Create a new MCP server configuration."""
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
    """Connect to the stored MCP server (initialize + tools/list) and report status.

    A real handshake, not a config check: returns connected + the live tool count, or
    connected=False with the failure reason.
    """
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
