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

from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from fleetent import audit_log, auth, connector_config_store, user_store

router = APIRouter(prefix="/admin")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}
_SENSITIVE = ("secret", "token", "refresh", "api_key", "password")


# --- injectable seams (connectors / mcp follow-ups) ---------------------------


def connectors_list_grants() -> list[dict[str, Any]]:
    """(user, connector) authorization matrix. Owned by connectors (placeholder).

    Each item: ``{user_id, connector_id, status, scopes}`` where status is one of
    not_authorized / authorized / needs_reauth / credential_error.
    """
    return []


def connectors_revoke(user_id: str, connector_id: str) -> dict[str, Any]:
    """Revoke a user's connector credential. Owned by connectors (placeholder)."""
    return {"user_id": user_id, "connector_id": connector_id, "revoked": False, "wired": False}


def connectors_offboarding_result(user_id: str) -> dict[str, Any]:
    """Result of connectors auto-revoking a disabled user's credentials. Placeholder."""
    return {"user_id": user_id, "revoked": [], "failed": []}


def connector_lifecycle_stats(connector_id: str) -> dict[str, Any]:
    """Refresh success/failure + re-auth counts for a connector. Placeholder."""
    return {"connector_id": connector_id, "refresh_ok": 0, "refresh_failed": 0, "reauths": 0}


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
    oauth_config: dict[str, Any] | None = None
    enabled: bool | None = None


# --- OAuth connector catalog --------------------------------------------------


@router.get("/connectors/grants")
def authorization_matrix(authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    grants = _mask(connectors_list_grants())
    # admin cannot complete a user's first consent — surface the hint, expose no route.
    return {
        "grants": grants,
        "consent_hint": "first consent must be completed by the user in their own browser; "
        "admin cannot authorize on their behalf",
    }


@router.get("/connectors/offboarding/{user_id}")
def offboarding_result(user_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    return _mask(connectors_offboarding_result(user_id))


@router.get("/connectors")
def list_connectors(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return [_mask(c) for c in connector_config_store.list_connectors()]


@router.post("/connectors")
def add_connector(body: ConnectorBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if body.protocol != "oauth2":
        raise HTTPException(status_code=422, detail="only OAuth 2.x connectors are supported")
    if connector_config_store.get_connector(body.id) is not None:
        raise HTTPException(status_code=409, detail="connector id already exists")
    connector_config_store.add_connector(
        body.id,
        body.display_name,
        oauth_config=body.oauth_config,
        protocol=body.protocol,
        enabled=body.enabled,
    )
    audit_log.write_audit(user.id, "connector.add", "connector", body.id)
    return _mask(connector_config_store.get_connector(body.id))


@router.put("/connectors/{connector_id}")
def edit_connector(
    connector_id: str, body: ConnectorEditBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if connector_config_store.get_connector(connector_id) is None:
        raise HTTPException(status_code=404, detail="connector not found")
    connector_config_store.edit_connector(connector_id, **body.model_dump(exclude_unset=True))
    audit_log.write_audit(user.id, "connector.edit", "connector", connector_id)
    return _mask(connector_config_store.get_connector(connector_id))


@router.get("/connectors/{connector_id}/lifecycle")
def lifecycle(connector_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    return connector_lifecycle_stats(connector_id)


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
    return _mask(result)


# --- MCP servers --------------------------------------------------------------


@router.get("/mcp/doctor")
def mcp_doctor_view(authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    return _mask(mcp_doctor())


@router.get("/mcp/servers")
def list_mcp_servers(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return [_mask(s) for s in mcp_list_servers()]


@router.get("/mcp/servers/{server_id}/tools")
def list_mcp_tools(
    server_id: str, authorization: str | None = Header(None)
) -> list[dict[str, Any]]:
    _current_user(authorization)
    return mcp_list_tools(server_id)


@router.post("/mcp/servers/{server_id}/reconnect")
def reconnect_mcp(server_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    result = mcp_reconnect(server_id)
    audit_log.write_audit(user.id, "mcp.reconnect", "mcp_server", server_id)
    return result
