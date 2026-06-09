"""Integration tests for the allow-always store (approval-minimization).

Real SQLite via an injected tmp db_path; verifies ensure_schema + grant/lookup/list
and idempotent re-grant.
"""

from __future__ import annotations

from pathlib import Path

from fleetent.governance import approval_allowlist_store as store


def _db(tmp_path: Path) -> Path:
    return tmp_path / "fleetent.db"


def test_grant_then_allowed(tmp_path: Path) -> None:
    db = _db(tmp_path)
    fp = store.fingerprint("user:alice", "run_code", {"code": "print(1)"})
    assert store.is_allowed(fp, db_path=db) is False
    store.add_grant(
        fingerprint=fp,
        scope_key="user:alice",
        tool_name="run_code",
        created_at="2026-06-09T00:00:00Z",
        created_by="slack:U_LEAD",
        db_path=db,
    )
    assert store.is_allowed(fp, db_path=db) is True


def test_unknown_fingerprint_not_allowed(tmp_path: Path) -> None:
    db = _db(tmp_path)
    store.ensure_schema(db)
    assert store.is_allowed("deadbeef" * 8, db_path=db) is False


def test_list_grants_returns_rows(tmp_path: Path) -> None:
    db = _db(tmp_path)
    fp = store.fingerprint("u", "t", {"x": 1})
    store.add_grant(
        fingerprint=fp,
        scope_key="u",
        tool_name="t",
        created_at="2026-06-09T00:00:00Z",
        db_path=db,
    )
    grants = store.list_grants(db_path=db)
    assert len(grants) == 1
    assert grants[0]["fingerprint"] == fp
    assert grants[0]["tool_name"] == "t"


def test_re_grant_is_idempotent(tmp_path: Path) -> None:
    db = _db(tmp_path)
    fp = store.fingerprint("u", "t", {"x": 1})
    for _ in range(3):
        store.add_grant(
            fingerprint=fp,
            scope_key="u",
            tool_name="t",
            created_at="2026-06-09T00:00:00Z",
            db_path=db,
        )
    assert len(store.list_grants(db_path=db)) == 1
