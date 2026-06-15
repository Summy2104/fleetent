from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

import pytest

from fleetent.platform.im_gateway_management import identity

_SQLITE_INTEGRITY_ERROR = __import__("sqlite3").IntegrityError


class _Result:
    def __init__(
        self,
        *,
        row: dict[str, Any] | tuple[Any, ...] | None = None,
        rows: list[dict[str, Any]] | None = None,
        rowcount: int = 1,
    ) -> None:
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self) -> dict[str, Any] | tuple[Any, ...] | None:
        return self._row

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Conn:
    def __init__(self, execute_impl) -> None:
        self._execute_impl = execute_impl

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> _Result:
        params = params or {}
        return self._execute_impl(sql, params)


def test_parse_meta_handles_empty_invalid_non_dict_and_dict() -> None:
    assert identity._parse_meta(None) == {}  # noqa: SLF001
    assert identity._parse_meta("not-json") == {}  # noqa: SLF001
    assert identity._parse_meta(json.dumps(["x"])) == {}  # noqa: SLF001
    assert identity._parse_meta(json.dumps({"team_id": "T1"})) == {"team_id": "T1"}  # noqa: SLF001


def test_check_allowed_by_user_id_follows_blocked_status(monkeypatch) -> None:
    monkeypatch.setattr(identity, "get_by_id", lambda user_id: None)
    assert identity.check_allowed_by_user_id("u1") is True

    monkeypatch.setattr(
        identity, "get_by_id", lambda user_id: type("U", (), {"status": "blocked"})()
    )
    assert identity.check_allowed_by_user_id("u1") is False


def test_get_or_create_returns_existing_user_without_creating(monkeypatch) -> None:
    @contextmanager
    def fake_conn():
        yield _Conn(lambda sql, params: _Result(row=("user-1",)))

    existing = object()
    monkeypatch.setattr(identity, "_conn", fake_conn)
    monkeypatch.setattr(identity, "get_by_id", lambda user_id: existing)
    monkeypatch.setattr(
        identity,
        "create_user",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("create_user must not run")),
    )

    assert identity.get_or_create("slack", "U1", "tenant-1") is existing


def test_get_or_create_creates_user_and_handles_insert_race(monkeypatch) -> None:
    class _Created:
        id = "created-user"

    rows = iter([None, ("existing-user",)])

    def execute(sql: str, params: dict[str, Any]) -> _Result:
        if sql.startswith("SELECT user_id FROM im_users"):
            return _Result(row=next(rows))
        return _Result(rowcount=0)

    @contextmanager
    def fake_conn():
        yield _Conn(execute)

    monkeypatch.setattr(identity, "_conn", fake_conn)
    monkeypatch.setattr(identity, "create_user", lambda **kwargs: (_Created(), "token"))
    monkeypatch.setattr(
        identity,
        "get_by_id",
        lambda user_id: {"existing-user": "existing", "created-user": _Created()}[user_id],
    )

    assert identity.get_or_create("slack", "U1", "tenant-1") == "existing"


def test_identity_fields_returns_copy_not_backed_by_module_constant() -> None:
    fields = identity.identity_fields("slack")
    fields[0]["label"] = "changed"

    assert identity.identity_fields("slack")[0]["label"] == "Display name"
    assert identity.identity_fields("unknown") == []


def test_get_im_user_returns_none_when_row_missing(monkeypatch) -> None:
    @contextmanager
    def fake_conn():
        yield _Conn(lambda sql, params: _Result(row=None))

    monkeypatch.setattr(identity, "_conn", fake_conn)

    assert identity.get_im_user(7) is None


def test_get_im_user_parses_metadata_and_allowed(monkeypatch) -> None:
    row = {
        "id": 7,
        "platform": "slack",
        "platform_user_id": "U1",
        "user_id": "user-1",
        "status": "active",
        "created_at": "2026-06-15T00:00:00+00:00",
        "meta_json": json.dumps({"team_id": "T1"}),
    }

    @contextmanager
    def fake_conn():
        yield _Conn(lambda sql, params: _Result(row=row))

    monkeypatch.setattr(identity, "_conn", fake_conn)

    got = identity.get_im_user(7)

    assert got == {
        "id": 7,
        "platform": "slack",
        "platform_user_id": "U1",
        "user_id": "user-1",
        "status": "active",
        "allowed": True,
        "created_at": "2026-06-15T00:00:00+00:00",
        "metadata": {"team_id": "T1"},
    }


def test_batch_block_im_builds_batch_id_and_calls_each_identity(monkeypatch) -> None:
    calls: list[tuple[int, str, str | None, str]] = []
    monkeypatch.setattr("secrets.token_hex", lambda n: "abc123")
    monkeypatch.setattr(
        identity,
        "block_im_user",
        lambda im_user_id, reason, actor, batch_id: calls.append(
            (im_user_id, reason, actor, batch_id)
        ),
    )

    batch_id = identity.batch_block_im([3, 4], reason="raid", actor="admin-1")

    assert batch_id == "batch-abc123"
    assert calls == [
        (3, "raid", "admin-1", "batch-abc123"),
        (4, "raid", "admin-1", "batch-abc123"),
    ]


def test_approve_and_block_user_delegate_to_specific_helpers(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        identity, "restore_im_user", lambda im_user_id: calls.append(("restore", im_user_id))
    )
    monkeypatch.setattr(
        identity, "block_im_user", lambda im_user_id: calls.append(("block", im_user_id))
    )

    identity.approve_user(7)
    identity.block_user(8)

    assert calls == [("restore", 7), ("block", 8)]


def test_update_im_identity_filters_metadata_and_audits(monkeypatch) -> None:
    executed: list[tuple[str, dict[str, Any]]] = []
    audits: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def execute(sql: str, params: dict[str, Any]) -> _Result:
        executed.append((sql, params))
        if sql.startswith("SELECT platform"):
            return _Result(row=("slack",))
        return _Result()

    @contextmanager
    def fake_conn():
        yield _Conn(execute)

    monkeypatch.setattr(identity, "_conn", fake_conn)
    monkeypatch.setattr(
        "fleetent.audit_log.write_audit",
        lambda *args, **kwargs: audits.append((args, kwargs)),
    )

    identity.update_im_identity(
        9,
        platform_user_id="U2",
        metadata={"display_name": "Ops", "email": "ops@example.com", "ignored": "x"},
        actor="admin-1",
    )

    assert executed[1][1] == {"puid": "U2", "id": 9}
    assert json.loads(executed[2][1]["m"]) == {
        "display_name": "Ops",
        "email": "ops@example.com",
    }
    assert audits == [
        (
            ("admin-1", "update_im_user"),
            {
                "target_type": "im_user",
                "target_id": "9",
                "detail": {
                    "platform_user_id": "U2",
                    "metadata_keys": ["display_name", "email"],
                },
            },
        )
    ]


def test_update_im_identity_raises_for_missing_row(monkeypatch) -> None:
    @contextmanager
    def fake_conn():
        yield _Conn(lambda sql, params: _Result(row=None))

    monkeypatch.setattr(identity, "_conn", fake_conn)

    with pytest.raises(ValueError, match="im identity not found"):
        identity.update_im_identity(99, metadata={"display_name": "Ops"})


def test_update_im_identity_surfaces_duplicate_platform_user_id(monkeypatch) -> None:
    def execute(sql: str, params: dict[str, Any]) -> _Result:
        if sql.startswith("SELECT platform"):
            return _Result(row=("slack",))
        if sql.startswith("UPDATE im_users SET platform_user_id"):
            raise _SQLITE_INTEGRITY_ERROR("duplicate")
        return _Result()

    @contextmanager
    def fake_conn():
        yield _Conn(execute)

    monkeypatch.setattr(identity, "_conn", fake_conn)

    with pytest.raises(ValueError, match="already exists"):
        identity.update_im_identity(9, platform_user_id="U2")


def test_delete_im_identity_requires_existing_row(monkeypatch) -> None:
    @contextmanager
    def fake_conn():
        yield _Conn(lambda sql, params: _Result(rowcount=0))

    monkeypatch.setattr(identity, "_conn", fake_conn)

    with pytest.raises(ValueError, match="im identity not found"):
        identity.delete_im_identity(8)


def test_block_restore_and_rebind_im_identity_cover_success_and_errors(monkeypatch) -> None:
    audits: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        "fleetent.audit_log.write_audit",
        lambda *args, **kwargs: audits.append((args, kwargs)),
    )
    monkeypatch.setattr(
        identity,
        "get_im_user",
        lambda im_user_id: {"user_id": "user-1"} if im_user_id == 7 else None,
    )
    status_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        identity, "set_status", lambda user_id, status: status_calls.append((user_id, status))
    )

    identity.block_im_user(7, reason="raid", actor="admin-1", batch_id="b1")
    identity.restore_im_user(7, reason="ok", actor="admin-1", batch_id="b2")
    assert status_calls == [("user-1", "blocked"), ("user-1", "active")]

    with pytest.raises(ValueError, match="im identity not found"):
        identity.block_im_user(9)
    with pytest.raises(ValueError, match="im identity not found"):
        identity.restore_im_user(9)

    @contextmanager
    def fake_conn():
        yield _Conn(lambda sql, params: _Result(rowcount=1))

    monkeypatch.setattr(identity, "_conn", fake_conn)
    monkeypatch.setattr(
        identity, "get_by_id", lambda user_id: object() if user_id == "user-2" else None
    )
    identity.rebind_im_identity(7, "user-2", actor="admin-2")

    with pytest.raises(ValueError, match="target user not found"):
        identity.rebind_im_identity(7, "missing")

    @contextmanager
    def fake_missing_conn():
        yield _Conn(lambda sql, params: _Result(rowcount=0))

    monkeypatch.setattr(identity, "_conn", fake_missing_conn)
    monkeypatch.setattr(identity, "get_by_id", lambda user_id: object())
    with pytest.raises(ValueError, match="im identity not found"):
        identity.rebind_im_identity(7, "user-2")


def test_list_helpers_return_allowed_and_parsed_metadata(monkeypatch) -> None:
    rows = [
        {
            "id": 1,
            "platform": "slack",
            "platform_user_id": "U1",
            "user_id": "user-1",
            "status": "active",
            "created_at": "2026-06-15T00:00:00+00:00",
            "meta_json": json.dumps({"display_name": "Ops"}),
        },
        {
            "id": 2,
            "platform": "telegram",
            "platform_user_id": "123",
            "user_id": "user-1",
            "status": "blocked",
            "created_at": "2026-06-15T00:01:00+00:00",
            "meta_json": None,
        },
    ]

    @contextmanager
    def fake_conn():
        yield _Conn(lambda sql, params: _Result(rows=rows))

    monkeypatch.setattr(identity, "_conn", fake_conn)

    assert identity.list_im_identities("user-1") == [
        {
            "id": 1,
            "platform": "slack",
            "platform_user_id": "U1",
            "status": "active",
            "allowed": True,
            "metadata": {"display_name": "Ops"},
        },
        {
            "id": 2,
            "platform": "telegram",
            "platform_user_id": "123",
            "status": "blocked",
            "allowed": False,
            "metadata": {},
        },
    ]
    assert identity.list_all() == [
        {
            "id": 1,
            "platform": "slack",
            "platform_user_id": "U1",
            "user_id": "user-1",
            "status": "active",
            "allowed": True,
            "created_at": "2026-06-15T00:00:00+00:00",
            "metadata": {"display_name": "Ops"},
        },
        {
            "id": 2,
            "platform": "telegram",
            "platform_user_id": "123",
            "user_id": "user-1",
            "status": "blocked",
            "allowed": False,
            "created_at": "2026-06-15T00:01:00+00:00",
            "metadata": {},
        },
    ]
