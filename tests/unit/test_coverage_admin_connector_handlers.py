from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from fleetent import agent_store
from fleetent.platform.agent_management_console import agent_admin_api, agent_console_api
from fleetent.platform.connector_management import connector_admin_api


@dataclass
class _User:
    id: str = "admin"
    role: str = "admin"


def _agent() -> agent_store.Agent:
    return agent_store.Agent(
        id=7,
        name="ops",
        system_prompt="Be useful",
        allowed_tools=["search"],
        active_version_id=3,
        features={"code_execution": True},
        plugins=["plugin-a"],
        allowed_skills=["skill-a"],
        tenant_id="tenant",
        team_id="team",
        skills_dir="skills",
        mcp_server_ids=["global", "agent-only"],
        model_overrides={"model": "fast"},
        memory_namespace="ops",
    )


def _patch_agent_admin_auth(monkeypatch: pytest.MonkeyPatch, module: Any) -> None:
    monkeypatch.setattr(module, "_current_user", lambda _authorization: _User(role="viewer"))
    monkeypatch.setattr(module, "_require_admin", lambda _authorization: _User())
    monkeypatch.setattr(module.audit_log, "write_audit", lambda *args, **kwargs: None)


def test_agent_admin_yaml_bindings_versions_and_deploy(monkeypatch, tmp_path):
    _patch_agent_admin_auth(monkeypatch, agent_admin_api)
    agent = _agent()
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(agent_admin_api.agent_store, "get_by_name", lambda name: agent)
    monkeypatch.setattr(
        agent_admin_api.agent_store,
        "list_mcp_servers_for_agent",
        lambda _agent_id: ["global", "missing"],
    )
    monkeypatch.setattr(
        agent_admin_api.mcp_server_store,
        "get_mcp_server",
        lambda agent_id, sid: (
            {
                "server_id": sid,
                "transport": "sse",
                "url": "https://mcp.local",
                "auth_type": "bearer",
                "api_key_env": "MCP_KEY",
                "command": "",
                "args": None,
                "env": None,
            }
            if sid == "global" and agent_id is None
            else None
        ),
    )
    monkeypatch.setattr(
        agent_admin_api.agent_store, "list_users_for_agent", lambda _agent_id: ["u1"]
    )
    monkeypatch.setattr(
        agent_admin_api.agent_store,
        "list_versions",
        lambda name: [SimpleNamespace(id=1, version=1, is_active=False, created_at="now")],
    )
    monkeypatch.setattr(
        agent_admin_api.agent_store,
        "activate_version",
        lambda *args: calls.append(("activate", args, {})),
    )
    monkeypatch.setattr(agent_admin_api.paths, "base_dir", lambda: tmp_path)

    exported = agent_admin_api.export_agent_yaml("ops", authorization="Session token")
    assert exported["agent"] == "ops"
    assert "mcp_servers:" in exported["yaml"]
    assert "bindings:" in exported["yaml"]

    deployed = agent_admin_api.deploy_agent("ops", authorization="Session token")
    assert deployed["deployed"] is True
    assert (tmp_path / "agents" / "ops" / "agent.yaml").exists()
    assert agent_admin_api.list_versions("ops", authorization="Session token")[0]["version"] == 1
    assert agent_admin_api.activate_version("ops", 2, authorization="Session token") == {
        "name": "ops",
        "active_version": 2,
    }
    assert calls == [("activate", ("ops", 2), {})]

    with pytest.raises(HTTPException) as exc:
        agent_admin_api.deploy_agent("../bad", authorization="Session token")
    assert exc.value.status_code == 400


def test_agent_admin_binding_skill_kb_oauth_and_mcp_handlers(monkeypatch):
    _patch_agent_admin_auth(monkeypatch, agent_admin_api)
    agent = _agent()
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(agent_admin_api.agent_store, "get_by_name", lambda name: agent)
    for name in (
        "assign_user",
        "unassign_user",
        "bind_mcp_server",
        "unbind_mcp_server",
    ):
        monkeypatch.setattr(
            agent_admin_api.agent_store,
            name,
            lambda *args, _name=name, **kwargs: calls.append((_name, args, kwargs)),
        )
    monkeypatch.setattr(agent_admin_api.agent_store, "list_users_for_agent", lambda _agent_id: [])
    monkeypatch.setattr(
        agent_admin_api.agent_store, "list_mcp_servers_for_agent", lambda _agent_id: ["db"]
    )
    monkeypatch.setattr(
        agent_admin_api.agent_im_group_store,
        "list_groups_for_agent",
        lambda _agent_id: [{"platform": "slack", "group_id": "C1"}],
    )
    monkeypatch.setattr(
        agent_admin_api.mcp_server_store,
        "list_mcp_servers",
        lambda _agent_id: [{"server_id": "db"}],
    )
    monkeypatch.setattr(
        agent_admin_api.skill_admin_store,
        "enabled_skill_names",
        lambda agent_id: {"skill-a"},
    )
    monkeypatch.setattr(
        agent_admin_api.skill_admin_store,
        "list_skills_for_agent",
        lambda agent_id: [{"skill_name": "skill-b", "enabled": False}],
    )
    monkeypatch.setattr(
        agent_admin_api.skill_admin_store,
        "set_binding",
        lambda *args, **kwargs: calls.append(("set_binding", args, kwargs)),
    )
    monkeypatch.setattr(
        agent_admin_api.skill_registry,
        "list_skills",
        lambda: [{"name": "skill-a"}, {"name": "skill-c"}],
    )
    monkeypatch.setattr(
        agent_admin_api.agent_kbs_store,
        "list_kbs_for_agent",
        lambda tenant_id, agent_id: ["kb1"],
    )
    monkeypatch.setattr(
        agent_admin_api.agent_kbs_store,
        "bind",
        lambda *args, **kwargs: calls.append(("kb_bind", args, kwargs)),
    )
    monkeypatch.setattr(
        agent_admin_api.agent_kbs_store,
        "unbind",
        lambda *args: calls.append(("kb_unbind", args, {})),
    )
    monkeypatch.setattr(
        agent_admin_api.agent_service_grant_store,
        "list_services_for_agent",
        lambda agent_id: [{"service_id": "gdrive", "run_as": "user"}],
    )
    monkeypatch.setattr(
        agent_admin_api.agent_service_grant_store,
        "bind",
        lambda *args, **kwargs: calls.append(("oauth_bind", args, kwargs)),
    )
    monkeypatch.setattr(
        agent_admin_api.agent_service_grant_store,
        "unbind",
        lambda *args: calls.append(("oauth_unbind", args, {})),
    )
    monkeypatch.setattr(
        agent_admin_api.external_service_store,
        "get_service",
        lambda connector_id: {"service_id": connector_id} if connector_id == "gdrive" else None,
    )

    assert agent_admin_api.bind_user("ops", "u1", authorization="Session token")["bound"]
    assert not agent_admin_api.unbind_user("ops", "u1", authorization="Session token")["bound"]
    assert agent_admin_api.get_bindings("ops", authorization="Session token") == {
        "users": [],
        "mcp_servers": ["db"],
        "groups": [{"platform": "slack", "group_id": "C1"}],
    }
    assert agent_admin_api.list_agent_skills("ops", authorization="Session token") == [
        {"skill_name": "skill-a", "enabled": True},
        {"skill_name": "skill-b", "enabled": False},
        {"skill_name": "skill-c", "enabled": False},
    ]
    assert agent_admin_api.set_agent_skill(
        "ops", "skill-a", enabled=False, authorization="Session token"
    ) == {"agent": "ops", "skill_name": "skill-a", "enabled": False}
    assert agent_admin_api.bind_mcp("ops", "db", authorization="Session token")["bound"]
    assert not agent_admin_api.unbind_mcp("ops", "db", authorization="Session token")["bound"]
    assert agent_admin_api.list_agent_kbs("ops", authorization="Session token") == {
        "agent": "ops",
        "kb_ids": ["kb1"],
    }
    assert agent_admin_api.bind_agent_kb("ops", "kb1", authorization="Session token")["bound"]
    assert not agent_admin_api.unbind_agent_kb("ops", "kb1", authorization="Session token")["bound"]
    assert agent_admin_api.list_agent_oauth("ops", authorization="Session token") == {
        "agent": "ops",
        "service_grants": [{"service_id": "gdrive", "run_as": "user"}],
        "connector_ids": ["gdrive"],
    }
    assert agent_admin_api.bind_oauth("ops", "gdrive", authorization="Session token")["bound"]
    assert not agent_admin_api.unbind_oauth("ops", "gdrive", authorization="Session token")["bound"]
    with pytest.raises(HTTPException) as missing_mcp:
        agent_admin_api.bind_mcp("ops", "missing", authorization="Session token")
    assert missing_mcp.value.status_code == 404
    with pytest.raises(HTTPException) as missing_oauth:
        agent_admin_api.bind_oauth("ops", "missing", authorization="Session token")
    assert missing_oauth.value.status_code == 404


def test_agent_console_agent_lifecycle(monkeypatch):
    _patch_agent_admin_auth(monkeypatch, agent_console_api)
    defs: dict[str, dict[str, Any]] = {
        "ops": {
            "id": 7,
            "system_prompt": "Be useful",
            "allowed_tools": ["search"],
            "plugins": ["plugin-a"],
            "features": {"x": True},
            "skills_dir": "skills",
            "mcp_server_ids": ["mcp"],
            "model_overrides": {"model": "fast"},
            "memory_namespace": "ops",
        }
    }
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(agent_console_api, "get_agent_def", lambda name: defs.get(name))
    monkeypatch.setattr(
        agent_console_api,
        "create_agent_def",
        lambda name, *args, **kwargs: (
            defs.__setitem__(
                name,
                {
                    "id": len(defs) + 10,
                    "system_prompt": args[0],
                    "allowed_tools": args[1],
                    "plugins": kwargs.get("plugins", []),
                    "features": kwargs.get("features", {}),
                },
            ),
            calls.append(("create", (name, *args), kwargs)),
        ),
    )
    monkeypatch.setattr(
        agent_console_api,
        "update_agent_def",
        lambda *args, **kwargs: calls.append(("update", args, kwargs)),
    )
    monkeypatch.setattr(agent_console_api, "delete_agent_def", lambda name: True)
    monkeypatch.setattr(
        agent_console_api, "references_for", lambda name: {"users": [], "channels": []}
    )
    # Dual-state read seams (wired to real stores by server import) must be stubbed in
    # this DB-less unit test. enable is gated on placement: pretend "ops" is pinned.
    monkeypatch.setattr(
        agent_console_api, "get_agent_placement", lambda agent_id: {"node_id": "node-a"}
    )
    monkeypatch.setattr(agent_console_api, "get_agent_runtime", lambda agent_id: None)
    monkeypatch.setattr(agent_console_api, "list_agent_runtimes", lambda: [])
    monkeypatch.setattr(agent_console_api, "list_agent_placements", lambda: [])
    monkeypatch.setattr(
        agent_console_api, "agent_observability_agg", lambda name, window: {"calls": 3}
    )
    state = {"provenance": "managed", "status": "enabled"}
    monkeypatch.setattr(agent_console_api.agent_admin_store, "get_state", lambda name: state)
    for method in (
        "set_provenance",
        "enable",
        "mark_drift",
        "delete_state",
        "disable",
        "archive",
        "restore",
    ):
        monkeypatch.setattr(
            agent_console_api.agent_admin_store,
            method,
            lambda *args, _method=method, **kwargs: calls.append((_method, args, kwargs)),
        )
    monkeypatch.setattr(
        agent_console_api.agent_admin_store, "list_states", lambda include_archived=False: [state]
    )

    assert agent_console_api.list_agents(authorization="Session token") == [state]
    assert agent_console_api.observability("ops", authorization="Session token") == {"calls": 3}
    created = agent_console_api.create_agent(
        agent_console_api.CreateBody(
            name="new-agent",
            capabilities_yaml=(
                "allowed_tools:\n  - shell\nplugins:\n  - p\nfeatures:\n  flag: true\n"
            ),
        ),
        authorization="Session token",
    )
    assert created["agent"] == "new-agent"
    assert (
        agent_console_api.get_agent("ops", authorization="Session token")["system_prompt"]
        == "Be useful"
    )
    assert (
        agent_console_api.update_agent(
            "ops",
            agent_console_api.UpdateBody(system_prompt="Updated"),
            authorization="Session token",
        )["agent"]
        == "ops"
    )
    assert agent_console_api.delete_agent(
        "ops", authorization="Session token", x_confirm="true"
    ) == {
        "agent": "ops",
        "deleted": True,
    }
    assert (
        agent_console_api.enable_agent("ops", authorization="Session token")["status"] == "enabled"
    )
    assert (
        agent_console_api.disable_agent("ops", authorization="Session token")["status"]
        == "disabled"
    )
    assert (
        agent_console_api.archive_agent("ops", authorization="Session token", x_confirm="true")[
            "status"
        ]
        == "archived"
    )
    assert (
        agent_console_api.restore_agent("ops", authorization="Session token")["status"] == "enabled"
    )
    assert agent_console_api.clone_agent(
        "ops", agent_console_api.CloneBody(new_name="clone"), authorization="Session token"
    ) == {"agent": "clone", "cloned_from": "ops", "provenance": "adhoc"}
    with pytest.raises(HTTPException) as bad_yaml:
        agent_console_api.create_agent(
            agent_console_api.CreateBody(name="bad", capabilities_yaml="- not-map"),
            authorization="Session token",
        )
    assert bad_yaml.value.status_code == 422


async def test_connector_admin_catalog_mcp_and_grant_handlers(monkeypatch):
    _patch_agent_admin_auth(monkeypatch, connector_admin_api)
    connectors = {
        "gdrive": {
            "id": "gdrive",
            "display_name": "Drive",
            "enabled": True,
            "oauth_config": {"client_secret": "secret", "nested": [{"refresh_token": "tok"}]},
        }
    }
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        connector_admin_api,
        "connectors_list_grants",
        lambda agent_id=None: [{"connector_id": "gdrive", "access_token": "secret"}],
    )
    monkeypatch.setattr(
        connector_admin_api,
        "connectors_offboarding_result",
        lambda user_id: {"user_id": user_id, "refresh_token": "secret"},
    )
    monkeypatch.setattr(
        connector_admin_api,
        "connectors_revoke",
        lambda user_id, connector_id: {
            "user_id": user_id,
            "connector_id": connector_id,
            "token": "secret",
        },
    )
    monkeypatch.setattr(
        connector_admin_api,
        "connector_lifecycle_stats",
        lambda connector_id: {
            "active_grants": 2,
            "last_refresh_success": True,
            "last_refresh_at": "now",
        },
    )
    monkeypatch.setattr(
        connector_admin_api.external_service_store,
        "list_services",
        lambda: [
            {
                "service_id": "gdrive",
                "display_name": "Drive",
                "protocol": "oauth2",
                "enabled": True,
                "oauth_config": {"client_secret": "secret", "nested": [{"refresh_token": "tok"}]},
            }
        ],
    )
    monkeypatch.setattr(
        connector_admin_api.external_service_store,
        "get_service",
        lambda connector_id: (
            {
                "service_id": connector_id,
                "display_name": connectors[connector_id]["display_name"],
                "protocol": connectors[connector_id].get("protocol", "oauth2"),
                "enabled": connectors[connector_id]["enabled"],
                "oauth_config": connectors[connector_id]["oauth_config"],
            }
            if connector_id in connectors
            else None
        ),
    )
    monkeypatch.setattr(
        connector_admin_api.external_service_store,
        "add_service",
        lambda id, display_name, **kwargs: connectors.setdefault(
            id,
            {
                "id": id,
                "display_name": display_name,
                "protocol": kwargs.get("protocol", "oauth2"),
                "enabled": kwargs.get("enabled", True),
                "oauth_config": kwargs.get("oauth_config") or {},
            },
        ),
    )
    monkeypatch.setattr(
        connector_admin_api.external_service_store,
        "edit_service",
        lambda connector_id, **kwargs: connectors[connector_id].update(kwargs),
    )
    monkeypatch.setattr(
        connector_admin_api.external_service_store,
        "delete_service",
        lambda connector_id: connectors.pop(connector_id, None),
    )
    monkeypatch.setattr(
        connector_admin_api,
        "mcp_list_servers",
        lambda: [{"id": "runtime", "transport": "stdio", "api_key_env": "SECRET"}],
    )
    monkeypatch.setattr(
        connector_admin_api, "mcp_doctor", lambda: {"checks": [{"api_key": "secret"}]}
    )
    monkeypatch.setattr(
        connector_admin_api, "mcp_reconnect", lambda server_id: {"server_id": server_id}
    )

    async def fake_probe(server_id: str) -> dict[str, Any]:
        return {"connected": True, "tool_count": 2, "tools": [{"name": "tool"}]}

    async def fake_sync(server_id: str, agent_id: int | None) -> None:
        calls.append(("sync", (server_id, agent_id), {}))

    monkeypatch.setattr(connector_admin_api, "mcp_probe", fake_probe)
    monkeypatch.setattr(connector_admin_api, "mcp_sync_server", fake_sync)
    mcp_rows = {
        (None, "stored"): {
            "server_id": "stored",
            "transport": "http",
            "url": "https://mcp",
            "command": "",
            "args": None,
            "enabled": True,
            "agent_id": None,
        }
    }
    monkeypatch.setattr(
        connector_admin_api.mcp_server_store,
        "list_mcp_servers",
        lambda agent_id: [row for (aid, _sid), row in mcp_rows.items() if aid == agent_id],
    )
    monkeypatch.setattr(
        connector_admin_api.mcp_server_store,
        "get_mcp_server",
        lambda agent_id, server_id: mcp_rows.get((agent_id, server_id)),
    )
    monkeypatch.setattr(
        connector_admin_api.mcp_server_store,
        "add_mcp_server",
        lambda **kwargs: mcp_rows.__setitem__(
            (kwargs.get("agent_id"), kwargs["server_id"]),
            {
                "server_id": kwargs["server_id"],
                "transport": kwargs["transport"],
                "url": kwargs["url"],
                "command": kwargs["command"],
                "args": kwargs["args"],
                "enabled": True,
                "agent_id": kwargs.get("agent_id"),
            },
        ),
    )
    monkeypatch.setattr(
        connector_admin_api.mcp_server_store,
        "edit_mcp_server",
        lambda agent_id, server_id, **kwargs: calls.append(
            ("edit_mcp", (agent_id, server_id), kwargs)
        ),
    )
    monkeypatch.setattr(
        connector_admin_api.mcp_server_store,
        "delete_mcp_server",
        lambda agent_id, server_id: calls.append(("delete_mcp", (agent_id, server_id), {})),
    )

    assert (
        connector_admin_api.authorization_matrix(authorization="Session token")["grants"][0][
            "access_token"
        ]
        == "****"
    )
    assert (
        connector_admin_api.offboarding_result("u1", authorization="Session token")["refresh_token"]
        == "****"
    )
    assert (
        connector_admin_api.list_connectors(authorization="Session token")[0]["oauth_config"][
            "client_secret"
        ]
        == "****"
    )
    assert (
        connector_admin_api.add_connector(
            connector_admin_api.ConnectorBody(id="slack", display_name="Slack"),
            authorization="Session token",
        )["id"]
        == "slack"
    )
    assert (
        connector_admin_api.edit_connector(
            "slack",
            connector_admin_api.ConnectorEditBody(display_name="Slack New", enabled=False),
            authorization="Session token",
        )["display_name"]
        == "Slack New"
    )
    assert connector_admin_api.test_oauth_connector("slack", authorization="Session token")[
        "token_valid"
    ]
    assert (
        connector_admin_api.lifecycle("slack", authorization="Session token")["active_grants"] == 2
    )
    assert (
        connector_admin_api.revoke_grant(
            "u1", "slack", authorization="Session token", x_confirm="true"
        )["token"]
        == "****"
    )
    assert connector_admin_api.delete_connector("slack", authorization="Session token") == {
        "success": True,
        "connector_id": "slack",
    }
    with pytest.raises(HTTPException) as protocol_error:
        connector_admin_api.add_connector(
            connector_admin_api.ConnectorBody(id="bad", display_name="Bad", protocol="api_key"),
            authorization="Session token",
        )
    assert protocol_error.value.status_code == 422
    assert (
        connector_admin_api.mcp_doctor_view(authorization="Session token")["checks"][0]["api_key"]
        == "****"
    )
    assert {
        server["id"]
        for server in connector_admin_api.list_mcp_servers(authorization="Session token")
    } == {
        "runtime",
        "stored",
    }
    assert await connector_admin_api.list_mcp_tools("stored", authorization="Session token") == {
        "connected": True,
        "tools": [{"name": "tool"}],
        "error": None,
    }
    assert connector_admin_api.reconnect_mcp("stored", authorization="Session token") == {
        "server_id": "stored"
    }
    assert await connector_admin_api.edit_mcp_server(
        "stored", {"enabled": False}, authorization="Session token"
    ) == {"success": True, "server_id": "stored"}
    assert await connector_admin_api.create_mcp_server(
        {"id": "new", "transport": "stdio"}, authorization="Session token"
    ) == {"success": True, "server_id": "new"}
    assert await connector_admin_api.test_mcp_server("stored", authorization="Session token") == {
        "success": True,
        "server_id": "stored",
        "transport": "http",
        "tools_count": 2,
        "connected": True,
        "tool_count": 2,
        "tools": [{"name": "tool"}],
    }
    assert await connector_admin_api.delete_mcp_server("stored", authorization="Session token") == {
        "success": True,
        "server_id": "stored",
    }
    assert calls[-1] == ("sync", ("stored", None), {})
