"""Unit tests: structured logging calls in session.manager module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

# ── session.manager uses custom logger ───────────────────────────────────────


def test_session_manager_logger_is_custom() -> None:
    import fleetent.session.manager as mgr
    from fleetent.observability.structured_logging import Logger

    assert isinstance(mgr._logger, Logger)


def test_session_manager_has_no_structlog_import() -> None:
    import ast
    import pathlib

    src = pathlib.Path("src/fleetent/session/manager.py").read_text()
    tree = ast.parse(src)
    structlog_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and any(
            (getattr(a, "name", None) or getattr(node, "module", None) or "").startswith(
                "structlog"
            )
            for a in getattr(node, "names", [{"name": ""}])
        )
    ]
    assert structlog_imports == [], "session/manager.py must not import structlog"


# ── cleanup_expired logs via _logger ─────────────────────────────────────────


def test_cleanup_expired_logs_info_on_completion(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    with patch("fleetent.session.manager._logger") as mock_log:
        mgr.cleanup_expired(ttl_seconds=0, _now=1e12)

    mock_log.info.assert_called()


def test_cleanup_expired_logs_info_per_deleted_session(tmp_path: Path, monkeypatch) -> None:
    import time

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    # Create an expired session file
    p = tmp_path / "old-sess.json"
    p.write_text('{"meta":{},"messages":[]}')
    os.utime(p, (0, 0))  # mtime = epoch, definitely expired

    with patch("fleetent.session.manager._logger") as mock_log:
        removed = mgr.cleanup_expired(ttl_seconds=1, _now=time.time())

    assert "old-sess" in removed
    # Should log individual deletion info + summary
    assert mock_log.info.call_count >= 2


def test_cleanup_expired_logs_warn_on_delete_failure(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    p = tmp_path / "failing.json"
    p.write_text("{}")
    os.utime(p, (0, 0))

    with (
        patch("fleetent.session.manager._logger") as mock_log,
        patch.object(Path, "unlink", side_effect=OSError("permission denied")),
    ):
        mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    mock_log.warn.assert_called()


# ── enforce_capacity logs via _logger ────────────────────────────────────────


def test_enforce_capacity_logs_info_on_eviction(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    # Create 3 session files; limit to 1 → 2 evictions
    for i in range(3):
        p = tmp_path / f"sess-{i}.json"
        p.write_text('{"meta":{},"messages":[]}')
        os.utime(p, (i, i))  # mtimes 0, 1, 2 → sess-0 is oldest

    with patch("fleetent.session.manager._logger") as mock_log:
        removed = mgr.enforce_capacity(max_count=1)

    assert len(removed) == 2
    mock_log.info.assert_called()


# ── maybe_run_maintenance logs via _logger ───────────────────────────────────


def test_maybe_run_maintenance_uses_custom_logger(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mgr, "_last_cleanup_at", None)  # open gate

    with patch("fleetent.session.manager._logger") as mock_log:
        mgr.maybe_run_maintenance(_now=1e12)

    # Should have logged via _logger (not structlog)
    assert mock_log.info.called or mock_log.warn.called or mock_log.debug.called


# ── list_session_ids limit ────────────────────────────────────────────────────


def test_list_session_ids_limit_truncates(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    for i in range(10):
        (tmp_path / f"s{i}.json").write_text("{}")

    result = mgr.list_session_ids(limit=3)
    assert len(result) == 3


def test_list_session_ids_no_limit_returns_all(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    for i in range(5):
        (tmp_path / f"s{i}.json").write_text("{}")

    result = mgr.list_session_ids()
    assert len(result) == 5


# ── list_by_user exposed via manager ─────────────────────────────────────────


def test_session_mgr_exposes_list_by_user() -> None:
    from fleetent import session as session_pkg

    assert hasattr(session_pkg, "list_by_user"), (
        "list_by_user must be exported from session package"
    )


# ── save token_usage parameter ────────────────────────────────────────────────


async def test_save_with_token_usage_calls_add_token_usage(tmp_path: Path, monkeypatch) -> None:
    from unittest.mock import patch

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mgr, "_last_cleanup_at", __import__("time").time())  # gate closed

    with (
        patch("fleetent.session.index.record_activity"),
        patch("fleetent.platform.chat_management.session_admin_store.add_token_usage") as mock_add,
    ):
        await mgr.save("tok-save", [{"role": "user", "content": "hi"}], token_usage=(120, 80))

    mock_add.assert_called_once_with("tok-save", 120, 80)


async def test_save_without_token_usage_does_not_call_add(tmp_path: Path, monkeypatch) -> None:
    from unittest.mock import patch

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mgr, "_last_cleanup_at", __import__("time").time())

    with (
        patch("fleetent.session.index.record_activity"),
        patch("fleetent.platform.chat_management.session_admin_store.add_token_usage") as mock_add,
    ):
        await mgr.save("no-tok", [{"role": "user", "content": "hi"}])

    mock_add.assert_not_called()


async def test_save_token_usage_failure_does_not_break_save(tmp_path: Path, monkeypatch) -> None:
    from unittest.mock import patch

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mgr, "_last_cleanup_at", __import__("time").time())

    with (
        patch("fleetent.session.index.record_activity"),
        patch(
            "fleetent.platform.chat_management.session_admin_store.add_token_usage",
            side_effect=RuntimeError("db locked"),
        ),
    ):
        await mgr.save("tok-fail", [{"role": "user", "content": "hi"}], token_usage=(10, 5))

    # session file still written despite token failure
    assert (tmp_path / "tok-fail.json").exists()
