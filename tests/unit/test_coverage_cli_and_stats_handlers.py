from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from fleetent.knowledge_base import operations as kb_operations
from fleetent.platform.admin_cli import agents, kb_connectors, users
from fleetent.platform.agent_statistics import stats_admin_api


@dataclass
class _CliUser:
    id: str = "u1"
    name: str = "Alice Long Display Name"
    created_at: str = "2026-01-01T00:00:00Z"


def _ns(**values: Any) -> argparse.Namespace:
    return argparse.Namespace(**values)


def test_agent_cli_handles_version_user_and_default_flows(monkeypatch, tmp_path, capsys):
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
        model_policy=SimpleNamespace(model_dump=lambda mode="json": {"routes": {"default": []}}),
        memory_namespace="ops",
    )

    import yaml

    agents_dir = tmp_path / "agents"
    (agents_dir / "ops").mkdir(parents=True)
    (agents_dir / "ops" / "agent.yaml").write_text(yaml.safe_dump({"name": "ops", "version": 1}))
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(agents_dir))
    monkeypatch.setitem(
        sys.modules,
        "fleetent.agent_store",
        SimpleNamespace(
            _UNSET=object(),
            get_by_name=lambda name: fake_agent if name == "ops" else None,
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

    assert agents.handle(_ns(cmd="set-default-agent", clear=False, agent_name="ops"))
    ops_yaml = yaml.safe_load((agents_dir / "ops" / "agent.yaml").read_text())
    assert ops_yaml["bindings"]["default"] is True
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
    assert "version 2" in output
    assert "name: ops" in output
    assert ("assign_user", ("u1", 9), {}) in calls

    with pytest.raises(SystemExit):
        agents.handle(_ns(cmd="list-agent-versions", agent_name="x"))
    with pytest.raises(SystemExit):
        agents.handle(_ns(cmd="show-agent", agent_name="x"))
    with pytest.raises(SystemExit):
        agents.handle(_ns(cmd="assign-user", user_id="u1", agent_name="x"))


def test_user_cli_handles_create_list_rotate_and_builtin_admin(monkeypatch, capsys):
    user = _CliUser()
    monkeypatch.setattr(users, "create_user", lambda name: (_CliUser(name=name), "ma-newkey"))
    monkeypatch.setattr(users, "list_users", lambda: [user, _CliUser(id="u2", name="B" * 25)])
    monkeypatch.setattr(users, "rotate_key", lambda user_id: (user, "ma-rotated"))
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
    assert audit_calls  # export writes an audit entry
