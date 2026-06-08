"""Unit tests: agent-side resume marker (.resume sibling file)."""

from __future__ import annotations

import os
from pathlib import Path


def test_mark_then_is_resume_pending(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    mgr.mark_resume_pending("s1")
    assert (tmp_path / "s1.resume").exists()
    assert mgr.is_resume_pending("s1") is True


def test_is_resume_pending_false_when_absent(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    assert mgr.is_resume_pending("nope") is False


def test_clear_resume_pending_removes_file(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    mgr.mark_resume_pending("s2")
    mgr.clear_resume_pending("s2")
    assert not (tmp_path / "s2.resume").exists()
    assert mgr.is_resume_pending("s2") is False


def test_clear_resume_pending_absent_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    mgr.clear_resume_pending("never")  # no raise


def test_mark_resume_pending_slash_session_id(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    mgr.mark_resume_pending("slack:C1/U2")
    assert (tmp_path / "slack:C1" / "U2.resume").exists()
    assert mgr.is_resume_pending("slack:C1/U2") is True


def test_scan_and_mark_recent_resume_marks_window(tmp_path: Path, monkeypatch) -> None:

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    recent = tmp_path / "recent.json"
    recent.write_text('{"meta":{},"messages":[]}')  # mtime = now (recent)

    marked = mgr.scan_and_mark_recent_resume(window_seconds=120)

    assert "recent" in marked
    assert mgr.is_resume_pending("recent") is True


def test_scan_and_mark_recent_resume_skips_old(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    old = tmp_path / "old.json"
    old.write_text('{"meta":{},"messages":[]}')
    os.utime(old, (0, 0))  # ancient mtime

    marked = mgr.scan_and_mark_recent_resume(window_seconds=120)

    assert "old" not in marked
    assert mgr.is_resume_pending("old") is False


def test_session_package_exports_resume_funcs() -> None:
    from fleetent import session as session_pkg

    for fn in (
        "mark_resume_pending",
        "is_resume_pending",
        "clear_resume_pending",
        "scan_and_mark_recent_resume",
    ):
        assert hasattr(session_pkg, fn), f"{fn} must be exported"


def test_cleanup_expired_removes_resume_marker(tmp_path: Path, monkeypatch) -> None:
    from unittest.mock import patch

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    main = tmp_path / "exp.json"
    main.write_text('{"meta":{},"messages":[]}')
    os.utime(main, (0, 0))
    marker = tmp_path / "exp.resume"
    marker.touch()

    with patch("fleetent.session.index.delete_batch"):
        removed = mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    assert "exp" in removed
    assert not marker.exists()  # resume marker removed alongside main file


def test_resume_marker_not_treated_as_session(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    (tmp_path / "x.resume").touch()
    # .resume must not appear as a session in the scan
    assert mgr.list_session_ids() == []
