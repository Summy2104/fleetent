from __future__ import annotations

import argparse
import sys
from types import SimpleNamespace
from typing import Any

from fleetent.platform.agent_statistics import stats_admin_api
from fleetent.platform.platform_cli import users


def _ns(**values: Any) -> argparse.Namespace:
    return argparse.Namespace(**values)


def test_user_cli_only_keeps_seed_builtin_admin(monkeypatch, capsys) -> None:
    monkeypatch.setitem(
        sys.modules,
        "fleetent.auth",
        SimpleNamespace(seed_builtin_admin=lambda: (SimpleNamespace(name="admin"), "temp-pass")),
    )

    assert users.handle(_ns(cmd="seed-builtin-admin"))
    assert not users.handle(_ns(cmd="create-user", name="Alice"))
    assert not users.handle(_ns(cmd="rotate-key", user_id="u1"))

    output = capsys.readouterr().out
    assert "Built-in admin created." in output


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
    assert audit_calls
