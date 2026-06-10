"""Integration tests: approvals 表 schema 漂移自愈（approvals-schema-drift-hotfix）。

覆盖三种存量表形态（旧/新/双列）+ 重复幂等 + 并发补列吞错。真实 SQLite schema
lifecycle，故属 integration 层；用 tmp_path 隔离，不触碰 data/。
"""

from __future__ import annotations

import sqlite3

import pytest

from fleetent.governance import approval_store

# ── 形态构造 helpers ──────────────────────────────────────────────────────────

_OLD_FORM_DDL = """
CREATE TABLE approvals (
    id                TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL,
    requester_user_id TEXT NOT NULL,
    risk_level        TEXT NOT NULL,
    tool_name         TEXT NOT NULL,
    tool_args         TEXT NOT NULL,
    status            TEXT NOT NULL,
    approver_user_id  TEXT,
    created_at        TEXT NOT NULL,
    resolved_at       TEXT
)
"""

_DUAL_FORM_DDL = """
CREATE TABLE approvals (
    id                TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL,
    requester_user_id TEXT NOT NULL,
    risk_level        TEXT NOT NULL,
    tool_name         TEXT NOT NULL,
    tool_args         TEXT NOT NULL,
    status            TEXT NOT NULL,
    approver_user_id  TEXT,
    created_at        TEXT NOT NULL,
    resolved_at       TEXT,
    approver_actor    TEXT
)
"""


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "approvals_drift.db"


def _cols(db_path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[1] for r in conn.execute("PRAGMA table_info(approvals)")}
    finally:
        conn.close()


def _seed_old_form(db_path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_OLD_FORM_DDL)
        conn.execute(
            "INSERT INTO approvals (id, session_id, requester_user_id, risk_level, "
            "tool_name, tool_args, status, approver_user_id, created_at, resolved_at) "
            "VALUES ('a1','s1','req1','medium','run_code','{}','approved',"
            "'slack:U_OLD','2026-01-01T00:00:00+00:00','2026-01-01T01:00:00+00:00')"
        )
        conn.commit()
    finally:
        conn.close()


# ── 形态 O：旧库自愈 + 回填 ─────────────────────────────────────────────────


def test_old_form_self_heals_adds_column(db_path) -> None:
    """旧形态（仅 approver_user_id）经 ensure_schema 后补上 approver_actor 列。"""
    _seed_old_form(db_path)
    assert "approver_actor" not in _cols(db_path)

    approval_store.ensure_schema(db_path)

    assert "approver_actor" in _cols(db_path)


def test_old_form_backfills_from_legacy_column(db_path) -> None:
    """补列后历史行的 approver_actor 取自旧列 approver_user_id。"""
    _seed_old_form(db_path)

    approval_store.ensure_schema(db_path)

    rows = approval_store.list_approvals(db_path=db_path)
    assert rows[0]["approver_actor"] == "slack:U_OLD"


def test_old_form_update_approval_succeeds_after_heal(db_path) -> None:
    """自愈后 update_approval 引用 approver_actor 不再抛 no such column。"""
    _seed_old_form(db_path)
    approval_store.ensure_schema(db_path)

    approval_store.update_approval(
        id="a1",
        status="approved",
        resolved_at="2026-01-01T02:00:00+00:00",
        approver_actor="slack:U_NEW",
        db_path=db_path,
    )

    rows = approval_store.list_approvals(db_path=db_path)
    assert rows[0]["approver_actor"] == "slack:U_NEW"


# ── 形态 N：新库 no-op ───────────────────────────────────────────────────────


def test_new_form_is_noop(db_path) -> None:
    """当前 DDL 新建库（已有 approver_actor、无 approver_user_id）不被改动。"""
    approval_store.ensure_schema(db_path)  # 新建
    cols_before = _cols(db_path)
    assert "approver_actor" in cols_before
    assert "approver_user_id" not in cols_before

    approval_store.ensure_schema(db_path)  # 再次

    assert _cols(db_path) == cols_before  # 不引入 approver_user_id，结构不变


# ── 幂等 ─────────────────────────────────────────────────────────────────────


def test_old_form_double_call_idempotent(db_path) -> None:
    """旧库连续两次 ensure_schema：第二次不报错，结构数据一致。"""
    _seed_old_form(db_path)
    approval_store.ensure_schema(db_path)
    cols_after_first = _cols(db_path)
    actor_after_first = approval_store.list_approvals(db_path=db_path)[0]["approver_actor"]

    approval_store.ensure_schema(db_path)  # 幂等

    assert _cols(db_path) == cols_after_first
    assert approval_store.list_approvals(db_path=db_path)[0]["approver_actor"] == actor_after_first


# ── 形态 B：双列不回填 ───────────────────────────────────────────────────────


def test_dual_form_does_not_backfill(db_path) -> None:
    """两列都在、approver_actor 为 NULL 的历史行：ensure_schema 不回填，保持 NULL。"""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_DUAL_FORM_DDL)
        conn.execute(
            "INSERT INTO approvals (id, session_id, requester_user_id, risk_level, "
            "tool_name, tool_args, status, approver_user_id, created_at, approver_actor) "
            "VALUES ('b1','s1','req1','medium','run_code','{}','approved',"
            "'slack:U_OLD','2026-01-01T00:00:00+00:00', NULL)"
        )
        conn.commit()
    finally:
        conn.close()

    approval_store.ensure_schema(db_path)

    rows = approval_store.list_approvals(db_path=db_path)
    assert rows[0]["approver_actor"] is None  # 未被回填


# ── 并发：duplicate column 被吞 ───────────────────────────────────────────────


def test_concurrent_duplicate_column_swallowed(db_path, monkeypatch) -> None:
    """模拟竞态：探测报缺列但列已存在 → ALTER 抛 duplicate column → 被识别为已自愈不抛。"""
    approval_store.ensure_schema(db_path)  # 新建（已有 approver_actor）
    # 强制探测为「缺列」，逼出 ALTER 路径
    monkeypatch.setattr(approval_store, "_approvals_has_column", lambda *a, **k: False)

    # 不应抛出（duplicate column 被吞）
    approval_store.ensure_schema(db_path)


def test_non_duplicate_operational_error_not_swallowed(db_path, monkeypatch) -> None:
    """其它 OperationalError 必须照常抛出，不被吞。"""
    approval_store.ensure_schema(db_path)
    monkeypatch.setattr(approval_store, "_approvals_has_column", lambda *a, **k: False)

    def _boom(*a, **k):
        raise sqlite3.OperationalError("some other failure")

    monkeypatch.setattr(approval_store, "_add_approver_actor_column", _boom)
    with pytest.raises(sqlite3.OperationalError, match="some other failure"):
        approval_store.ensure_schema(db_path)
