from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from fleetent import user_store
from fleetent.intelligence.knowledge_base import operations as kb_operations
from fleetent.platform.admin_cli import agents, im_connectors, kb_connectors, users
from fleetent.platform.agent_statistics import stats_admin_api


@dataclass
class _CliUser:
    id: str = "u1"
    name: str = "Alice Long Display Name"
    api_key: str = "ma-secret"
    created_at: str = "2026-01-01T00:00:00Z"


def _ns(**values: Any) -> argparse.Namespace:
    return argparse.Namespace(**values)


def test_agent_cli_handles_channel_version_user_and_default_flows(monkeypatch, tmp_path, capsys):
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    fake_agent = SimpleNamespace(id=9)
    fake_version = SimpleNamespace(id=3, version=2, is_active=True, created_at="now")
    fake_snapshot = SimpleNamespace(
        name="ops",
        version=2,
        system_prompt="prompt",
        allowed_tools=["search"],
        skills_dir="skills",
        mcp_server_ids=["mcp"],
        model_overrides={"model": "fast"},
        memory_namespace="ops",
    )

    monkeypatch.setattr(agents, "_SETTINGS_YAML", tmp_path / "settings.yaml")
    monkeypatch.setitem(
        sys.modules,
        "fleetent.agent_store",
        SimpleNamespace(
            _UNSET=object(),
            get_by_name=lambda name: fake_agent if name == "ops" else None,
            assign_channel=lambda *args: calls.append(("assign_channel", args, {})),
            unassign_channel=lambda *args: calls.append(("unassign_channel", args, {})),
            create_version=lambda *args, **kwargs: fake_version,
            list_versions=lambda name: [fake_version] if name == "ops" else [],
            activate_version=lambda *args: calls.append(("activate_version", args, {})),
            assign_user=lambda *args: calls.append(("assign_user", args, {})),
            unassign_user=lambda *args: calls.append(("unassign_user", args, {})),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "fleetent.runtime.snapshot",
        SimpleNamespace(load_active_db=lambda name: fake_snapshot if name == "ops" else None),
    )

    assert agents.handle(
        _ns(cmd="assign-channel", platform="slack", channel_id="C1", agent_name="ops")
    )
    assert agents.handle(_ns(cmd="unassign-channel", platform="slack", channel_id="C1"))
    assert agents.handle(_ns(cmd="set-default-agent", clear=False, agent_name="ops"))
    assert "default_agent_name" in (tmp_path / "settings.yaml").read_text(encoding="utf-8")
    assert agents.handle(_ns(cmd="set-default-agent", clear=True, agent_name=None))
    assert agents.handle(
        _ns(
            cmd="update-agent",
            agent_name="ops",
            system_prompt="prompt",
            allowed_tools="search, shell",
            skills_dir="skills",
            mcp_server_ids="mcp",
            memory_namespace="mem",
            no_activate=False,
        )
    )
    assert agents.handle(_ns(cmd="list-agent-versions", agent_name="ops"))
    assert agents.handle(_ns(cmd="activate-agent-version", agent_name="ops", version=2))
    assert agents.handle(_ns(cmd="show-agent", agent_name="ops"))
    assert agents.handle(_ns(cmd="assign-user", user_id="u1", agent_name="ops"))
    assert agents.handle(_ns(cmd="unassign-user", user_id="u1", agent_name="ops"))
    assert not agents.handle(_ns(cmd="unknown"))

    output = capsys.readouterr().out
    assert "Channel slack/C1" in output
    assert "version 2" in output
    assert "name: ops" in output
    assert ("assign_user", ("u1", 9), {}) in calls

    with pytest.raises(SystemExit):
        agents.handle(_ns(cmd="assign-channel", platform="slack", channel_id="C1", agent_name="x"))
    with pytest.raises(SystemExit):
        agents.handle(_ns(cmd="list-agent-versions", agent_name="x"))
    with pytest.raises(SystemExit):
        agents.handle(_ns(cmd="show-agent", agent_name="x"))
    with pytest.raises(SystemExit):
        agents.handle(_ns(cmd="assign-user", user_id="u1", agent_name="x"))


def test_user_cli_handles_create_list_rotate_and_builtin_admin(monkeypatch, capsys):
    user = _CliUser()
    monkeypatch.setattr(users, "create_user", lambda name: _CliUser(name=name))
    monkeypatch.setattr(users, "list_users", lambda: [user, _CliUser(id="u2", name="B" * 25)])
    monkeypatch.setattr(users, "rotate_key", lambda user_id: user)
    monkeypatch.setitem(
        sys.modules,
        "fleetent.auth",
        SimpleNamespace(seed_builtin_admin=lambda: (SimpleNamespace(name="admin"), "temp-pass")),
    )

    assert users.handle(_ns(cmd="create-user", name="Alice"))
    assert users.handle(_ns(cmd="list-users"))
    assert users.handle(_ns(cmd="rotate-key", user_id="u1"))
    assert users.handle(_ns(cmd="seed-builtin-admin"))
    assert not users.handle(_ns(cmd="unknown"))

    output = capsys.readouterr().out
    assert "User created." in output
    assert "Alice Long Displa..." in output
    assert "Built-in admin created." in output

    monkeypatch.setattr(users, "list_users", lambda: [])
    assert users.handle(_ns(cmd="list-users"))
    monkeypatch.setattr(users, "rotate_key", lambda user_id: (_ for _ in ()).throw(KeyError()))
    with pytest.raises(SystemExit):
        users.handle(_ns(cmd="rotate-key", user_id="missing"))
    monkeypatch.setitem(
        sys.modules, "fleetent.auth", SimpleNamespace(seed_builtin_admin=lambda: None)
    )
    assert users.handle(_ns(cmd="seed-builtin-admin"))


def test_im_connector_cli_uses_mocked_management_boundaries(monkeypatch, capsys):
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    fake_im = SimpleNamespace(
        seed_from_env=lambda: ["slack"],
        list_connectors=lambda: [
            {"owner_id": "admin", "platform": "slack", "enabled": 1, "status": "connected"}
        ],
        resolve_masked=lambda owner, platform: {"bot_token": "***"},
        set_enabled=lambda *args: calls.append(("set_enabled", args, {})),
        set_config=lambda *args: calls.append(("set_config", args, {})),
        add_entry=lambda *args: calls.append(("add_entry", args, {})),
        remove_entry=lambda *args: calls.append(("remove_entry", args, {})),
        list_entries=lambda owner, platform: [
            {"id": 1, "platform": "slack", "scope_type": "channel", "scope_id": "C1", "note": "ok"}
        ],
    )
    monkeypatch.setattr(user_store, "admin_owner_id", lambda: "admin")
    monkeypatch.setattr(
        "fleetent.platform.im_gateway_management",
        fake_im,
        raising=False,
    )

    assert im_connectors.handle(_ns(cmd="seed-connectors"))
    assert im_connectors.handle(_ns(cmd="im-connector", im_connector_cmd="list"))
    assert im_connectors.handle(
        _ns(cmd="im-connector", im_connector_cmd="enable", platform="slack")
    )
    assert im_connectors.handle(
        _ns(cmd="im-connector", im_connector_cmd="set-config", platform="slack", set=["a=b"])
    )
    assert im_connectors.handle(
        _ns(
            cmd="im-channel",
            im_channel_cmd="allow",
            platform="slack",
            scope_type="channel",
            scope_id="C1",
            note="ok",
        )
    )
    assert im_connectors.handle(_ns(cmd="im-channel", im_channel_cmd="disallow", id=1))
    assert im_connectors.handle(_ns(cmd="im-channel", im_channel_cmd="list", platform="slack"))
    assert not im_connectors.handle(_ns(cmd="unknown"))

    output = capsys.readouterr().out
    assert "Seeded: slack" in output
    assert "bot_token=***" in output
    assert "allowed slack channel:C1" in output
    assert ("set_config", ("admin", "slack", {"a": "b"}), {}) in calls

    with pytest.raises(SystemExit):
        im_connectors.handle(
            _ns(cmd="im-connector", im_connector_cmd="set-config", platform="slack", set=["bad"])
        )


def test_kb_connector_cli_sync_guards_and_extract_summary(monkeypatch, capsys):
    async def check_connector(connector_id: str) -> SimpleNamespace:
        return SimpleNamespace(connector_id=connector_id, status="ok", message="token sk-secret")

    async def run_connector_sync(connector_id: str, dry_run: bool) -> SimpleNamespace:
        return SimpleNamespace(
            connector_id=connector_id,
            status="ok",
            summary={"documents": 2},
            error="",
        )

    monkeypatch.setattr(
        kb_operations,
        "list_configured_connectors",
        lambda: [
            SimpleNamespace(
                connector_id="gdrive",
                connector_type="google_drive",
                enabled=True,
                tenant_id="tenant",
                kb_id="kb",
                scope="folder",
            )
        ],
    )
    monkeypatch.setattr(kb_operations, "check_connector", check_connector)
    monkeypatch.setattr(
        kb_operations,
        "get_connector_status",
        lambda connector_id: SimpleNamespace(
            connector_id=connector_id,
            last_status="failed",
            last_summary={"documents": 1},
            last_error="Authorization: Bearer secret",
        ),
    )
    monkeypatch.setattr(kb_operations, "run_connector_sync", run_connector_sync)
    monkeypatch.setattr(
        kb_operations,
        "get_connector_config",
        lambda connector_id: SimpleNamespace(connector_type="google_drive"),
    )

    async def run_entity_extraction(*args: Any, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            status="ok",
            tenant_id="tenant",
            kb_id="kb",
            document_id="doc",
            documents_scanned=1,
            chunks_scanned=2,
            entities_upserted=3,
            mentions_written=4,
            relations_written=5,
            failed_count=0,
            error_summary="",
        )

    monkeypatch.setattr(
        kb_connectors,
        "run_entity_extraction",
        run_entity_extraction,
    )

    assert not kb_connectors.handle(_ns(cmd="not-kb"))
    assert kb_connectors.handle(_ns(cmd="kb", kb_cmd="connectors", connector_cmd="list"))
    assert kb_connectors.handle(
        _ns(cmd="kb", kb_cmd="connectors", connector_cmd="check", connector_id="gdrive")
    )
    assert kb_connectors.handle(
        _ns(cmd="kb", kb_cmd="connectors", connector_cmd="status", connector_id="gdrive")
    )
    assert kb_connectors.handle(
        _ns(
            cmd="kb",
            kb_cmd="connectors",
            connector_cmd="sync",
            connector_id="gdrive",
            dry_run=True,
            yes=False,
            pilot_fixture=False,
        )
    )
    assert kb_connectors.handle(
        _ns(cmd="kb", kb_cmd="extract-entities", tenant_id="tenant", kb_id="kb", document_id="doc")
    )

    output = capsys.readouterr().out
    assert "gdrive" in output
    assert "[REDACTED:token]" in output
    assert "documents=2" in output
    assert "entities_upserted=3" in output

    with pytest.raises(SystemExit):
        kb_connectors.handle(
            _ns(
                cmd="kb",
                kb_cmd="connectors",
                connector_cmd="sync",
                connector_id="gdrive",
                dry_run=False,
                yes=False,
                pilot_fixture=False,
            )
        )
    assert kb_connectors._execute_sync_env_flag("confluence") == "FLEETENT_CONFLUENCE_EXECUTE_SYNC"


def test_stats_admin_api_handlers_with_mocked_auth_and_data(monkeypatch):
    user = SimpleNamespace(id="viewer", role="viewer")
    admin = SimpleNamespace(id="admin", role="admin")
    traces = [
        {
            "agent_id": "a1",
            "user_id": "u1",
            "request_id": "r1",
            "session_id": "s1",
            "event": "tool_call",
            "tool": "search",
            "messages": [{"tool_calls": [{"name": "search"}]}],
            "tokens": 10,
            "latency_ms": 5,
            "model": "m",
        }
    ]
    monkeypatch.setattr(stats_admin_api, "_current_user", lambda authorization: user)
    monkeypatch.setattr(stats_admin_api, "fetch_traces", lambda **kwargs: traces)
    monkeypatch.setattr(
        stats_admin_api, "fetch_approvals", lambda agent_id=None: [{"approved": True}]
    )
    monkeypatch.setattr(
        stats_admin_api, "agent_allowed_tools", lambda agent_id: ["search", "shell"]
    )
    monkeypatch.setattr(stats_admin_api, "pricing_table", lambda: {"m": {"input": 1}})
    audit_calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(
        stats_admin_api.audit_log,
        "write_audit",
        lambda *args, **kwargs: audit_calls.append(args),
    )
    monkeypatch.setattr(stats_admin_api, "schedule_report", lambda *args: "task-1")

    assert stats_admin_api.overview("a1", authorization="Session token")["agent_id"] == "a1"
    assert stats_admin_api.compare("a1,a2", authorization="Session token")
    assert stats_admin_api.tools("a1", authorization="Session token")["coverage"]["used"] == [
        "search"
    ]
    assert stats_admin_api.per_user(authorization="Session token")[0]["user_id"] == "***"
    assert stats_admin_api.user_requests("u1", authorization="Session token")
    assert stats_admin_api.request_trace("r1", authorization="Session token")
    assert stats_admin_api.degraded_trace("s1", "u1", authorization="Session token")
    response = stats_admin_api.export(view="tools", agent_id="a1", authorization="Session token")
    assert response.media_type == "text/csv"

    monkeypatch.setattr(stats_admin_api, "_current_user", lambda authorization: admin)
    configured = stats_admin_api.configure_report(
        stats_admin_api.ReportBody(period="weekly", agent_id="a1", recipient="ops@example.com"),
        authorization="Session token",
    )
    assert configured == {"task_id": "task-1", "period": "weekly"}
    assert audit_calls

    monkeypatch.setattr(stats_admin_api, "_current_user", lambda authorization: user)
    with pytest.raises(HTTPException) as forbidden:
        stats_admin_api.configure_report(
            stats_admin_api.ReportBody(period="weekly", agent_id="a1", recipient="ops@example.com"),
            authorization="Session token",
        )
    assert forbidden.value.status_code == 403
    monkeypatch.setattr(stats_admin_api, "_current_user", lambda authorization: admin)
    with pytest.raises(HTTPException) as bad_period:
        stats_admin_api.configure_report(
            stats_admin_api.ReportBody(period="daily", agent_id="a1", recipient="ops@example.com"),
            authorization="Session token",
        )
    assert bad_period.value.status_code == 422
