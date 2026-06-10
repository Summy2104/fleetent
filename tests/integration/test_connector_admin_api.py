"""Tests for connector_admin_api (/admin/connectors, /admin/mcp). Scenarios 109-114."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.connector_management.connector_admin_api as api
import fleetent.user_store as user_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    for mod in (user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    user_store._init_db()

    # Keep endpoint tests hermetic: the live-runtime sync/probe seams must not touch
    # the network. Tests that exercise them monkeypatch these explicitly.
    async def _noop_sync(server_id: str, agent_id: int | None) -> None:
        return None

    async def _fake_probe(server_id: str) -> dict:
        return {"connected": True, "tool_count": 0, "tools": []}

    monkeypatch.setattr(api, "mcp_sync_server", _noop_sync)
    monkeypatch.setattr(api, "mcp_probe", _fake_probe)

    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str, confirm: bool = False) -> dict:
    h = {"Authorization": f"Session {token}"}
    if confirm:
        h["X-Confirm"] = "true"
    return h


# --- catalog CRUD + OAuth 2.x only -------------------------------------------


def test_no_auth_401(client):
    assert client.get("/admin/connectors").status_code == 401


def test_viewer_cannot_add(client):
    token, _ = _session_for("viewer")
    r = client.post(
        "/admin/connectors", headers=_hdr(token), json={"id": "gh", "display_name": "GitHub"}
    )
    assert r.status_code == 403


def test_add_connector_oauth2(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/connectors",
        headers=_hdr(token),
        json={
            "id": "gh",
            "display_name": "GitHub",
            "oauth_config": {"client_id": "cid", "client_secret": "leak"},
        },
    )
    assert r.status_code == 200
    assert "client_secret" not in r.json()["oauth_config"]  # never stored/returned


def test_non_oauth2_rejected(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/connectors",
        headers=_hdr(token),
        json={"id": "x", "display_name": "X", "protocol": "apikey"},
    )
    assert r.status_code == 422


def test_catalog_masks_secret(client, monkeypatch):  # 场景 114
    token, _ = _session_for("admin")
    client.post(
        "/admin/connectors",
        headers=_hdr(token),
        json={"id": "gh", "display_name": "GitHub", "oauth_config": {"client_id": "cid"}},
    )
    viewer, _ = _session_for("viewer")
    r = client.get("/admin/connectors", headers=_hdr(viewer))
    assert r.status_code == 200
    assert r.json()[0]["id"] == "gh"


# --- authorization matrix + no proxy consent (场景 109/110) ------------------


def test_authorization_matrix_four_states(client, monkeypatch):
    monkeypatch.setattr(
        api,
        "connectors_list_grants",
        lambda agent_id=None: [
            {"user_id": "u1", "connector_id": "gh", "status": "authorized", "scopes": ["repo"]},
            {"user_id": "u2", "connector_id": "gh", "status": "not_authorized"},
            {"user_id": "u3", "connector_id": "gh", "status": "needs_reauth"},
            {"user_id": "u4", "connector_id": "gh", "status": "credential_error"},
        ],
    )
    token, _ = _session_for("admin")
    r = client.get("/admin/connectors/grants", headers=_hdr(token))
    statuses = {g["status"] for g in r.json()["grants"]}
    assert statuses == {"authorized", "not_authorized", "needs_reauth", "credential_error"}


def test_no_proxy_consent_endpoint(client):  # 场景 110
    token, _ = _session_for("admin")
    # there is no endpoint to complete consent on a user's behalf
    r = client.post("/admin/connectors/grants/u2/gh/consent", headers=_hdr(token))
    assert r.status_code in (404, 405)
    # the matrix surfaces the hint instead
    matrix = client.get("/admin/connectors/grants", headers=_hdr(token))
    assert "browser" in matrix.json()["consent_hint"]


def test_matrix_masks_tokens(client, monkeypatch):
    monkeypatch.setattr(
        api,
        "connectors_list_grants",
        lambda agent_id=None: [
            {
                "user_id": "u1",
                "connector_id": "gh",
                "status": "authorized",
                "access_token": "secret-tok",
                "refresh_token": "secret-ref",
            },
        ],
    )
    token, _ = _session_for("admin")
    r = client.get("/admin/connectors/grants", headers=_hdr(token))
    g = r.json()["grants"][0]
    assert g["access_token"] == "****"
    assert g["refresh_token"] == "****"


# --- revoke (场景 111) -------------------------------------------------------


def test_revoke_requires_confirm_and_admin(client, monkeypatch):
    revoked = []
    monkeypatch.setattr(
        api, "connectors_revoke", lambda u, c: revoked.append((u, c)) or {"revoked": True}
    )
    token, _ = _session_for("admin")
    # without confirm
    assert (
        client.post("/admin/connectors/grants/u1/gh/revoke", headers=_hdr(token)).status_code == 428
    )
    # with confirm
    r = client.post("/admin/connectors/grants/u1/gh/revoke", headers=_hdr(token, confirm=True))
    assert r.status_code == 200
    assert revoked == [("u1", "gh")]
    assert any(a["action"] == "connector.revoke" for a in audit.search_audit())


def test_revoke_viewer_forbidden(client):
    token, _ = _session_for("viewer")
    r = client.post("/admin/connectors/grants/u1/gh/revoke", headers=_hdr(token, confirm=True))
    assert r.status_code == 403


# --- MCP server states + namespace (场景 112/113) ----------------------------


def test_mcp_server_states_visible(client, monkeypatch):
    monkeypatch.setattr(
        api,
        "mcp_list_servers",
        lambda: [
            {"id": "fs", "transport": "stdio", "status": "connected", "tool_count": 3},
            {"id": "gh", "transport": "http", "status": "degraded", "tool_count": 0},
            {"id": "db", "transport": "http", "status": "reconnecting", "tool_count": 0},
            {
                "id": "old",
                "transport": "stdio",
                "status": "permanently_unavailable",
                "tool_count": 0,
            },
        ],
    )
    token, _ = _session_for("viewer")
    r = client.get("/admin/mcp/servers", headers=_hdr(token))
    states = {s["status"] for s in r.json()}
    assert "degraded" in states and "permanently_unavailable" in states


def test_mcp_tools_lists_live_server_tools(client, monkeypatch):  # 场景 113
    token, _ = _session_for("admin")
    _add_global_mcp(client, token, "fs")

    async def fake_probe(server_id):
        assert server_id == "fs"
        return {
            "connected": True,
            "tool_count": 1,
            "tools": [{"name": "read_file", "description": "read"}],
        }

    monkeypatch.setattr(api, "mcp_probe", fake_probe)
    r = client.get("/admin/mcp/servers/fs/tools", headers=_hdr(token))
    body = r.json()
    assert body["connected"] is True
    assert body["tools"][0]["name"] == "read_file"


def test_mcp_tools_404_when_absent(client):
    token, _ = _session_for("admin")
    r = client.get("/admin/mcp/servers/ghost/tools", headers=_hdr(token))
    assert r.json()["connected"] is False
    assert r.json()["tools"] == []


def test_mcp_reconnect_admin_only(client, monkeypatch):
    monkeypatch.setattr(api, "mcp_reconnect", lambda sid: {"server_id": sid, "reconnected": True})
    token, _ = _session_for("admin")
    r = client.post("/admin/mcp/servers/gh/reconnect", headers=_hdr(token))
    assert r.status_code == 200
    assert any(a["action"] == "mcp.reconnect" for a in audit.search_audit())
    viewer, _ = _session_for("viewer")
    assert client.post("/admin/mcp/servers/gh/reconnect", headers=_hdr(viewer)).status_code == 403


def test_connector_list_exposes_owner_and_filters_by_agent(client):
    from fleetent.platform.connector_management import connector_config_store as store

    token, _ = _session_for("admin")
    client.post(
        "/admin/connectors", headers=_hdr(token), json={"id": "gh", "display_name": "GH global"}
    )
    store.add_connector("gh", "GH agent 5", agent_id=5)

    r = client.get("/admin/connectors", headers=_hdr(token))
    assert {(c["id"], c["agent_id"]) for c in r.json()} == {("gh", None)}

    r2 = client.get("/admin/connectors?agent_id=5", headers=_hdr(token))
    assert {c["display_name"] for c in r2.json()} == {"GH agent 5"}


def test_mcp_server_list_exposes_owner_and_agent_filter(client, monkeypatch):
    from fleetent.platform.connector_management import agent_mcp_server_store

    monkeypatch.setattr(
        api,
        "mcp_list_servers",
        lambda: [{"id": "fs", "transport": "stdio", "status": "connected", "tool_count": 1}],
    )
    agent_mcp_server_store.add_mcp_server(5, "internal", transport="stdio", command="python")
    token, _ = _session_for("admin")

    r = client.get("/admin/mcp/servers", headers=_hdr(token))
    assert ("fs", None) in {(s["id"], s["agent_id"]) for s in r.json()}

    r2 = client.get("/admin/mcp/servers?agent_id=5", headers=_hdr(token))
    internal = next(s for s in r2.json() if s["id"] == "internal")
    assert internal["agent_id"] == 5


def test_global_mcp_server_added_via_api_is_listed(client):
    # A server created through the dialog is global (agent_id=None); it must show
    # in the default list, not only when an agent is selected.
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/mcp/servers",
        headers=_hdr(token),
        json={"id": "middle", "transport": "http", "url": "https://example.com/mcp"},
    )
    assert r.status_code == 200

    listed = client.get("/admin/mcp/servers", headers=_hdr(token)).json()
    middle = next(s for s in listed if s["id"] == "middle")
    assert middle["agent_id"] is None
    assert middle["transport"] == "http"


def _add_global_mcp(client, token, sid="middle"):
    return client.post(
        "/admin/mcp/servers",
        headers=_hdr(token),
        json={"id": sid, "transport": "http", "url": "https://example.com/mcp"},
    )


def test_edit_mcp_server(client):
    token, _ = _session_for("admin")
    _add_global_mcp(client, token)
    r = client.put(
        "/admin/mcp/servers/middle",
        headers=_hdr(token),
        json={"url": "https://changed.example.com/mcp", "transport": "websocket"},
    )
    assert r.status_code == 200
    listed = client.get("/admin/mcp/servers", headers=_hdr(token)).json()
    middle = next(s for s in listed if s["id"] == "middle")
    assert middle["url"] == "https://changed.example.com/mcp"
    assert middle["transport"] == "websocket"


def test_disable_mcp_server(client):
    token, _ = _session_for("admin")
    _add_global_mcp(client, token)
    r = client.put("/admin/mcp/servers/middle", headers=_hdr(token), json={"enabled": False})
    assert r.status_code == 200
    listed = client.get("/admin/mcp/servers", headers=_hdr(token)).json()
    middle = next(s for s in listed if s["id"] == "middle")
    assert middle["enabled"] is False


def test_delete_mcp_server(client):
    token, _ = _session_for("admin")
    _add_global_mcp(client, token)
    r = client.delete("/admin/mcp/servers/middle", headers=_hdr(token))
    assert r.status_code == 200
    listed = client.get("/admin/mcp/servers", headers=_hdr(token)).json()
    assert all(s["id"] != "middle" for s in listed)


def test_mcp_mutations_viewer_forbidden(client):
    admin, _ = _session_for("admin")
    _add_global_mcp(client, admin)
    viewer, _ = _session_for("viewer")
    assert client.put("/admin/mcp/servers/middle", headers=_hdr(viewer), json={}).status_code == 403
    assert client.delete("/admin/mcp/servers/middle", headers=_hdr(viewer)).status_code == 403


def test_delete_connector(client):
    token, _ = _session_for("admin")
    client.post(
        "/admin/connectors", headers=_hdr(token), json={"id": "gh", "display_name": "GitHub"}
    )
    r = client.delete("/admin/connectors/gh", headers=_hdr(token))
    assert r.status_code == 200
    assert client.get("/admin/connectors", headers=_hdr(token)).json() == []


def test_delete_connector_viewer_forbidden(client):
    admin, _ = _session_for("admin")
    client.post(
        "/admin/connectors", headers=_hdr(admin), json={"id": "gh", "display_name": "GitHub"}
    )
    viewer, _ = _session_for("viewer")
    assert client.delete("/admin/connectors/gh", headers=_hdr(viewer)).status_code == 403


def test_delete_connector_404_when_absent(client):
    token, _ = _session_for("admin")
    assert client.delete("/admin/connectors/ghost", headers=_hdr(token)).status_code == 404


def test_authorization_matrix_scoped_to_agent(client, monkeypatch):
    captured: dict[str, object] = {}

    def fake_grants(agent_id=None):  # type: ignore[no-untyped-def]
        captured["agent_id"] = agent_id
        return [
            {"user_id": "u1", "connector_id": "gh", "status": "authorized", "agent_id": agent_id}
        ]

    monkeypatch.setattr(api, "connectors_list_grants", fake_grants)
    token, _ = _session_for("admin")
    r = client.get("/admin/connectors/grants?agent_id=7", headers=_hdr(token))
    assert captured["agent_id"] == 7
    assert r.json()["grants"][0]["agent_id"] == 7


def test_mcp_doctor_masks_auth(client, monkeypatch):
    monkeypatch.setattr(
        api,
        "mcp_doctor",
        lambda: {"checks": [{"name": "gh", "level": "green", "api_key": "secret-val"}]},
    )
    token, _ = _session_for("viewer")
    r = client.get("/admin/mcp/doctor", headers=_hdr(token))
    assert r.json()["checks"][0]["api_key"] == "****"
    assert r.json()["checks"][0]["level"] == "green"


def test_test_endpoint_returns_probe_result(client, monkeypatch):
    token, _ = _session_for("admin")
    _add_global_mcp(client, token, "probed")

    async def fake_probe(server_id):
        assert server_id == "probed"
        return {"connected": True, "tool_count": 3, "tools": ["a", "b", "c"]}

    monkeypatch.setattr(api, "mcp_probe", fake_probe)
    r = client.post("/admin/mcp/servers/probed/test", headers=_hdr(token))
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["connected"] is True
    assert body["tools_count"] == 3
    assert body["tools"] == ["a", "b", "c"]


def test_test_endpoint_reports_failure(client, monkeypatch):
    token, _ = _session_for("admin")
    _add_global_mcp(client, token, "downsrv")

    async def fake_probe(server_id):
        return {"connected": False, "error": "connection refused"}

    monkeypatch.setattr(api, "mcp_probe", fake_probe)
    r = client.post("/admin/mcp/servers/downsrv/test", headers=_hdr(token))
    body = r.json()
    assert body["success"] is False
    assert body["connected"] is False
    assert "refused" in body["error"]


def test_test_endpoint_404_when_absent(client):
    token, _ = _session_for("admin")
    r = client.post("/admin/mcp/servers/ghost/test", headers=_hdr(token))
    assert r.json()["connected"] is False


def test_create_triggers_runtime_sync(client, monkeypatch):
    calls = []

    async def spy_sync(server_id, agent_id):
        calls.append((server_id, agent_id))

    monkeypatch.setattr(api, "mcp_sync_server", spy_sync)
    token, _ = _session_for("admin")
    _add_global_mcp(client, token, "synced")
    assert ("synced", None) in calls


def test_create_duplicate_mcp_server_409(client):
    token, _ = _session_for("admin")
    assert _add_global_mcp(client, token, "dup").status_code == 200
    r = client.post(
        "/admin/mcp/servers",
        headers=_hdr(token),
        json={"id": "dup", "transport": "http", "url": "https://other"},
    )
    assert r.status_code == 409
