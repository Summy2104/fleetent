from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from fleetent import agent_store, server
from fleetent.platform.agent_management_console import agent_console_api
from fleetent.platform.askit_console import agent_apply_api
from fleetent.platform.node_management import node_store, placement_store


def _agent(**overrides: Any) -> agent_store.Agent:
    data = {
        "id": 7,
        "name": "ops",
        "system_prompt": "prompt",
        "allowed_tools": ["shell"],
        "active_version_id": 11,
        "features": {"code_execution": True},
        "plugins": ["github"],
        "allowed_skills": ["triage"],
        "tenant_id": "tenant-1",
        "team_id": "team-1",
        "skills_dir": "skills",
        "mcp_server_ids": ["files"],
        "model_overrides": {"default": "gpt"},
        "memory_namespace": "ops",
        "icon": "bot",
        "config_overrides": {"strict": True},
    }
    data.update(overrides)
    return agent_store.Agent(**data)


def test_connector_edge_tenant_and_im_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        server.agent_config,
        "current",
        lambda: SimpleNamespace(get=lambda owner_id: None if owner_id == "missing" else _agent()),
    )
    assert server._connector_edge_tenant("missing") == "default"
    assert server._connector_edge_tenant("ops") == "tenant-1"

    identity_user = SimpleNamespace(id="u1", status="active", tenant_id="tenant-1")
    monkeypatch.setattr(
        "fleetent.platform.im_gateway_management.identity.get_or_create",
        lambda platform, platform_user_id, edge_tenant: identity_user,
    )
    assert server._resolve_im_identity("ops", "slack", "U1") == "u1"

    blocked = SimpleNamespace(id="u2", status="blocked", tenant_id="tenant-1")
    monkeypatch.setattr(
        "fleetent.platform.im_gateway_management.identity.get_or_create",
        lambda platform, platform_user_id, edge_tenant: blocked,
    )
    with pytest.raises(server.IMIdentityResolutionError, match="blocked"):
        server._resolve_im_identity("ops", "slack", "U2")

    mismatch = SimpleNamespace(id="u3", status="active", tenant_id="tenant-2")
    monkeypatch.setattr(
        "fleetent.platform.im_gateway_management.identity.get_or_create",
        lambda platform, platform_user_id, edge_tenant: mismatch,
    )
    with pytest.raises(server.IMIdentityResolutionError, match="mismatch"):
        server._resolve_im_identity("ops", "slack", "U3")


def test_agent_def_dict_and_wire_agent_store_seams(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        server.agent_store, "get_version_by_id", lambda version_id: SimpleNamespace(version=3)
    )
    assert server._agent_def_dict(None) is None
    assert server._agent_def_dict(_agent())["version"] == 3
    # IM chat-type capability switches must round-trip through the console seam so
    # the detail endpoint can echo them back (otherwise the UI toggles read false).
    caps = server._agent_def_dict(_agent(supports_dm=True, supports_groups=True))
    assert caps["supports_dm"] is True
    assert caps["supports_groups"] is True

    created: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(server.agent_store, "get_by_name", lambda name: _agent(name=name))
    monkeypatch.setattr(
        server.agent_store,
        "create_agent",
        lambda *args, **kwargs: (
            created.append(("create_agent", args, kwargs)) or _agent(name=args[0])
        ),
    )
    monkeypatch.setattr(
        server.agent_store,
        "create_version",
        lambda *args, **kwargs: created.append(("create_version", args, kwargs)) or None,
    )
    monkeypatch.setattr(
        server.agent_store,
        "delete_agent",
        lambda name: created.append(("delete_agent", (name,), {})) or True,
    )
    monkeypatch.setattr(
        server.agent_store,
        "set_identity",
        lambda *args: created.append(("set_identity", args, {})),
    )
    monkeypatch.setattr(
        server.agent_store,
        "set_config_overrides",
        lambda *args: created.append(("set_config_overrides", args, {})),
    )
    server.wire_agent_store_seams()

    created_id = agent_apply_api.create_agent_def("ops", "prompt", ["shell"])
    assert created_id == 7
    agent_apply_api.update_agent_def("ops", "next", ["read"])
    assert agent_console_api.get_agent_def("ops")["id"] == 7
    agent_console_api.create_agent_def(
        "dev",
        "prompt",
        ["shell"],
        skills_dir="skills",
        mcp_server_ids=["files"],
        model_overrides={"default": "gpt"},
        memory_namespace="team",
        plugins=["github"],
        features={"code_execution": True},
        icon="bot",
        tenant_id="tenant-2",
        team_id="team-2",
        config_overrides={"strict": True},
    )
    agent_console_api.update_agent_def(
        "ops",
        "prompt-2",
        ["shell", "read"],
        skills_dir="skills-v2",
        mcp_server_ids=["files", "github"],
        model_overrides={"default": "gpt-2"},
        memory_namespace="prod",
        tenant_id="tenant-9",
        team_id=None,
        config_overrides={"strict": False},
    )
    assert agent_console_api.delete_agent_def("ops") is True

    assert any(name == "set_identity" for name, *_ in created)
    assert any(name == "set_config_overrides" for name, *_ in created)
    assert any(
        item[0] == "create_version" and item[2]["allowed_tools"] == ["shell", "read"]
        for item in created
    )


def test_wire_agent_store_seams_wires_dual_state_read_seams() -> None:
    server.wire_agent_store_seams()

    assert agent_console_api.get_agent_runtime is node_store.get_agent_status
    assert agent_console_api.get_agent_placement is placement_store.get_for_agent
    assert agent_console_api.list_agent_runtimes is node_store.list_agent_status
    assert agent_console_api.list_agent_placements is placement_store.list_placements


def test_server_does_not_import_run_stream() -> None:
    source = Path(server.__file__).read_text(encoding="utf-8")
    assert "from fleetent.runtime import run_stream" not in source


async def test_no_playground_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver_calls: list[tuple[str, Any]] = []
    assert not hasattr(server.chat_admin_api, "run_playground")
    monkeypatch.setattr(
        server.user_store, "set_api_key_resolver", lambda fn: resolver_calls.append(("api", fn))
    )
    monkeypatch.setattr(
        server.connectors, "set_provider", lambda fn: resolver_calls.append(("provider", fn))
    )
    monkeypatch.setattr(
        server, "set_im_identity_resolver", lambda fn: resolver_calls.append(("im", fn))
    )
    monkeypatch.setattr(
        server.agent_store, "set_delete_agent_hook", lambda fn: resolver_calls.append(("hook", fn))
    )
    monkeypatch.setattr(server, "scan_skills", lambda: resolver_calls.append(("skills", None)))
    monkeypatch.setattr(
        server.agent_config, "scan", lambda: resolver_calls.append(("agents", None))
    )
    monkeypatch.setattr(server, "load_plugins", lambda: resolver_calls.append(("plugins", None)))
    monkeypatch.setattr(
        "fleetent.runtime.approval_resume.reconcile_expired_approvals",
        AsyncMock(),
    )
    monkeypatch.setattr(
        server, "Settings", lambda: SimpleNamespace(database_url="sqlite:///tmp.db")
    )
    monkeypatch.setattr(
        server, "configure_logging", lambda settings: resolver_calls.append(("logging", settings))
    )
    monkeypatch.setattr(
        server, "log_config_loaded", lambda: resolver_calls.append(("loaded", None))
    )
    monkeypatch.setattr(
        server, "diagnose_database_writable", lambda url: resolver_calls.append(("db", url))
    )
    monkeypatch.setattr(
        server,
        "seed_builtin_admin",
        lambda: (SimpleNamespace(name="admin"), "temp-pass"),
    )
    monkeypatch.setattr("fleetent.integrations.mcp.aclose_all", AsyncMock())

    async with server.lifespan(SimpleNamespace()):
        assert ("skills", None) in resolver_calls
        assert ("plugins", None) in resolver_calls
        assert not hasattr(server.chat_admin_api, "run_playground")
        assert callable(server.chat_admin_api.load_transcript)
        assert callable(server.chat_admin_api.clear_session)
        assert callable(server.chat_admin_api.inject)
        assert callable(server.chat_admin_api.reset_session)


async def test_lifespan_wires_startup_and_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    resolver_calls: list[tuple[str, Any]] = []
    monkeypatch.setattr(
        server.user_store, "set_api_key_resolver", lambda fn: resolver_calls.append(("api", fn))
    )
    monkeypatch.setattr(
        server.connectors, "set_provider", lambda fn: resolver_calls.append(("provider", fn))
    )
    monkeypatch.setattr(
        server, "set_im_identity_resolver", lambda fn: resolver_calls.append(("im", fn))
    )
    monkeypatch.setattr(
        server.agent_store, "set_delete_agent_hook", lambda fn: resolver_calls.append(("hook", fn))
    )
    monkeypatch.setattr(server, "scan_skills", lambda: resolver_calls.append(("skills", None)))
    monkeypatch.setattr(
        server.agent_config, "scan", lambda: resolver_calls.append(("agents", None))
    )
    monkeypatch.setattr(server, "load_plugins", lambda: resolver_calls.append(("plugins", None)))
    monkeypatch.setattr(
        "fleetent.runtime.approval_resume.reconcile_expired_approvals",
        AsyncMock(),
    )
    monkeypatch.setattr(
        server, "Settings", lambda: SimpleNamespace(database_url="sqlite:///tmp.db")
    )
    monkeypatch.setattr(
        server, "configure_logging", lambda settings: resolver_calls.append(("logging", settings))
    )
    monkeypatch.setattr(
        server, "log_config_loaded", lambda: resolver_calls.append(("loaded", None))
    )
    monkeypatch.setattr(
        server, "diagnose_database_writable", lambda url: resolver_calls.append(("db", url))
    )
    monkeypatch.setattr(
        server,
        "seed_builtin_admin",
        lambda: (SimpleNamespace(name="admin"), "temp-pass"),
    )
    monkeypatch.setattr("fleetent.integrations.mcp.aclose_all", AsyncMock())

    async with server.lifespan(SimpleNamespace()):
        assert ("skills", None) in resolver_calls
        assert ("plugins", None) in resolver_calls
        assert callable(server.chat_admin_api.load_transcript)
        assert callable(server.chat_admin_api.clear_session)
        assert callable(server.chat_admin_api.inject)
        assert callable(server.chat_admin_api.reset_session)

    assert resolver_calls[-1] == ("im", None)


async def test_server_helper_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server, "_platform_bearer", lambda api_key: None)
    with pytest.raises(server.HTTPException, match="Invalid API key"):
        await server._authenticate("Bearer missing")

    monkeypatch.setattr(server, "list_approvals", lambda status=None: [{"status": status}])
    assert await server.get_approvals("pending") == [{"status": "pending"}]

    monkeypatch.setattr(
        server.agent_config,
        "current",
        lambda: SimpleNamespace(
            agents={
                "ops": SimpleNamespace(
                    im=SimpleNamespace(slack=object(), telegram=None),
                )
            }
        ),
    )
    assert server._slack_adapter_configured() is True
    assert server._telegram_adapter_configured() is False
