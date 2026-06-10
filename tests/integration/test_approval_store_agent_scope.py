"""Integration tests: approval_store and allowlist_store connect via set_state_db (3b-4).

Verifies:
- Both stores expose set_state_db() (no ensure_schema-into-global residual)
- No DB_PATH / create_database self-connection in source
- Store operations use the injected per-agent DB
- Store raises RuntimeError before set_state_db is called
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate


def _open_state_db(tmp_path: Path) -> SQLiteDatabase:
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, AGENT_STATE_MIGRATIONS)
    return db


# ── Guard: no self-connection in approval_store ───────────────────────────────


def test_approval_store_has_no_db_path_global() -> None:
    import fleetent.governance.approval_store as module

    source = inspect.getsource(module)
    assert "DB_PATH =" not in source, "approval_store must not have a DB_PATH global assignment"


def test_approval_store_has_no_ensure_schema() -> None:
    import fleetent.governance.approval_store as module

    source = inspect.getsource(module)
    assert "def ensure_schema" not in source, (
        "approval_store must not expose ensure_schema; schema is owned by agent_state MIGRATIONS"
    )


def test_allowlist_store_has_no_db_path_global() -> None:
    import fleetent.governance.approval_allowlist_store as module

    source = inspect.getsource(module)
    assert "DB_PATH =" not in source, "approval_allowlist_store must not have a DB_PATH global assignment"


def test_allowlist_store_has_no_ensure_schema() -> None:
    import fleetent.governance.approval_allowlist_store as module

    source = inspect.getsource(module)
    assert "def ensure_schema" not in source, (
        "approval_allowlist_store must not expose ensure_schema"
    )


# ── set_state_db is exposed ───────────────────────────────────────────────────


def test_approval_store_exposes_set_state_db() -> None:
    import fleetent.governance.approval_store as module

    assert hasattr(module, "set_state_db"), "approval_store must expose set_state_db()"
    assert callable(module.set_state_db)


def test_allowlist_store_exposes_set_state_db() -> None:
    import fleetent.governance.approval_allowlist_store as module

    assert hasattr(module, "set_state_db"), "approval_allowlist_store must expose set_state_db()"
    assert callable(module.set_state_db)


# ── RuntimeError before initialization ───────────────────────────────────────


def test_approval_store_raises_before_set_state_db(monkeypatch: pytest.MonkeyPatch) -> None:
    import fleetent.governance.approval_store as module

    monkeypatch.setattr(module, "_state_db", None)
    with pytest.raises(RuntimeError, match="set_state_db"):
        module.list_approvals()


def test_allowlist_store_raises_before_set_state_db(monkeypatch: pytest.MonkeyPatch) -> None:
    import fleetent.governance.approval_allowlist_store as module

    monkeypatch.setattr(module, "_state_db", None)
    with pytest.raises(RuntimeError, match="set_state_db"):
        module.list_grants()


# ── Operations use injected DB ────────────────────────────────────────────────


def test_approval_store_insert_uses_injected_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fleetent.governance.approval_store as module

    db = _open_state_db(tmp_path)
    monkeypatch.setattr(module, "_state_db", db)

    module.insert_approval(
        id="tst-1234",
        session_id="session:alice",
        requester_user_id="alice",
        risk_level="high",
        tool_name="delete_db",
        tool_args='{"table": "users"}',
        created_at="2026-01-01T00:00:00+00:00",
    )

    rows = module.list_approvals()
    assert len(rows) == 1
    assert rows[0]["id"] == "tst-1234"
    assert rows[0]["session_id"] == "session:alice"


def test_allowlist_store_add_grant_uses_injected_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import fleetent.governance.approval_allowlist_store as module

    db = _open_state_db(tmp_path)
    monkeypatch.setattr(module, "_state_db", db)

    fp = module.fingerprint("user:alice", "run_code", {"code": "print(1)"})
    assert module.is_allowed(fp) is False

    module.add_grant(
        fingerprint=fp,
        scope_key="user:alice",
        tool_name="run_code",
        created_at="2026-06-09T00:00:00Z",
        created_by="slack:U_LEAD",
    )
    assert module.is_allowed(fp) is True
