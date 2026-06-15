from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from fleetent import audit_log
from fleetent.governance import approval_router
from fleetent.identity import Principal
from fleetent.platform.user_management.platform_bearer_adapter import PlatformBearerAdapter


class _Result:
    def __init__(self, rows: list[tuple[Any, ...]] | None = None) -> None:
        self._rows = rows or []

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows


class _Conn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, dict[str, Any]]] = []
        self.rows: list[tuple[Any, ...]] = []

    def execute(self, sql: str, params: dict[str, Any]) -> _Result:
        self.executed.append((sql, params))
        return _Result(self.rows)

    def __enter__(self) -> "_Conn":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


def test_audit_log_write_and_search(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _Conn()
    conn.rows = [
        (
            1,
            "u1",
            "deploy",
            "agent",
            "ops",
            '{"strict": true}',
            "batch-1",
            "2026-06-15T00:00:00+00:00",
        )
    ]
    monkeypatch.setattr(audit_log, "_conn", lambda: conn)

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz: UTC | None = None) -> "_FakeDatetime":
            return cls(2026, 6, 15, tzinfo=UTC)

    monkeypatch.setattr(audit_log.datetime, "datetime", _FakeDatetime)
    audit_log.write_audit("u1", "deploy", "agent", "ops", {"strict": True}, "batch-1")
    found = audit_log.search_audit(
        actor="u1",
        action="deploy",
        target_type="agent",
        target_id="ops",
        since="2026-06-01T00:00:00+00:00",
        until="2026-06-30T00:00:00+00:00",
    )

    assert conn.executed[0][1]["detail"] == '{"strict": true}'
    assert "created_at >= :since" in conn.executed[1][0]
    assert found == [
        {
            "id": 1,
            "actor_user_id": "u1",
            "action": "deploy",
            "target_type": "agent",
            "target_id": "ops",
            "detail": {"strict": True},
            "batch_id": "batch-1",
            "created_at": "2026-06-15T00:00:00+00:00",
        }
    ]


async def test_approval_router_routes_subject_types(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_call = AsyncMock(return_value=True)
    reflection = AsyncMock(return_value=True)
    monkeypatch.setattr(approval_router, "_resolve_tool_call", tool_call)
    monkeypatch.setattr(approval_router, "_resolve_reflection_proposal", reflection)

    monkeypatch.setattr(
        approval_router.approval_request_store, "get_request", lambda approval_id: None
    )
    monkeypatch.setattr(
        approval_router.approval_store, "get_approval", lambda approval_id: {"id": approval_id}
    )
    assert await approval_router.resolve_approval_request(
        approval_id="a1",
        decision="approved",
        approver_user_id="u1",
        always=True,
        authorized_actors={"u1"},
    )
    tool_call.assert_awaited()

    monkeypatch.setattr(
        approval_router.approval_request_store,
        "get_request",
        lambda approval_id: {"subject_type": "memory_proposal"},
    )
    assert (
        await approval_router.resolve_approval_request(
            approval_id="a2",
            decision="rejected",
            approver_user_id="u2",
        )
        is True
    )
    reflection.assert_awaited()

    monkeypatch.setattr(
        approval_router.approval_request_store,
        "get_request",
        lambda approval_id: {"subject_type": "tool_call"},
    )
    assert await approval_router.resolve_approval_request(
        approval_id="a3",
        decision="approved",
        approver_user_id="u3",
    )

    monkeypatch.setattr(approval_router.approval_store, "get_approval", lambda approval_id: None)
    monkeypatch.setattr(
        approval_router.approval_request_store, "get_request", lambda approval_id: None
    )
    assert (
        await approval_router.resolve_approval_request(
            approval_id="missing",
            decision="approved",
            approver_user_id="u4",
        )
        is False
    )

    monkeypatch.setattr(
        approval_router.approval_request_store,
        "get_request",
        lambda approval_id: {"subject_type": "unknown"},
    )
    with pytest.raises(ValueError, match="unknown approval subject_type"):
        await approval_router.resolve_approval_request(
            approval_id="bad",
            decision="approved",
            approver_user_id="u5",
        )


def test_platform_bearer_adapter_resolves_or_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = PlatformBearerAdapter()
    monkeypatch.setattr(
        "fleetent.platform.user_management.api_key_store.resolve",
        lambda credentials: {"user_id": "u1"} if credentials == "ma-ok" else None,
    )
    monkeypatch.setattr(
        "fleetent.platform.user_management.platform_bearer_adapter.get_by_id",
        lambda user_id: SimpleNamespace(id=user_id, status="active", tenant_id="tenant-1"),
    )
    assert adapter("ma-ok") == Principal(user_id="u1", tenant_id="tenant-1")
    assert adapter("missing") is None

    monkeypatch.setattr(
        "fleetent.platform.user_management.platform_bearer_adapter.get_by_id",
        lambda user_id: SimpleNamespace(id=user_id, status="blocked", tenant_id="tenant-1"),
    )
    assert adapter("ma-ok") is None
