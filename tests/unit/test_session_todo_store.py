"""Unit tests: agent-side todo persistence (.todo sibling file).

Pure file I/O via monkeypatched SESSIONS_DIR (injectable file boundary), mirroring
test_session_resume_marker.py. No SQLite, no platform.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

ITEMS = [
    {"id": "1", "text": "task A", "status": "pending"},
    {"id": "2", "text": "task B", "status": "in_progress"},
]


def test_write_then_read_todo_round_trip(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    mgr.write_todo("s1", ITEMS)
    assert (tmp_path / "s1.todo").exists()
    assert mgr.read_todo("s1") == ITEMS


def test_read_todo_absent_returns_empty(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    assert mgr.read_todo("nope") == []


def test_write_todo_atomic_no_tmp_leftover(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    mgr.write_todo("s1", ITEMS)
    # No atomic-write temporary left behind; final file parses to the items.
    assert list(tmp_path.glob("*.tmp")) == []
    assert mgr.read_todo("s1") == ITEMS


def test_read_todo_corrupt_returns_empty(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    (tmp_path / "broken.todo").write_text("{not json")
    assert mgr.read_todo("broken") == []


def test_clear_todo_removes_file(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    mgr.write_todo("s2", ITEMS)
    mgr.clear_todo("s2")
    assert not (tmp_path / "s2.todo").exists()
    assert mgr.read_todo("s2") == []


def test_clear_todo_absent_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    mgr.clear_todo("never")  # no raise


def test_write_todo_slash_session_id_nests_in_subdir(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    mgr.write_todo("slack:C1/U2", ITEMS)
    assert (tmp_path / "slack:C1" / "U2.todo").exists()
    assert mgr.read_todo("slack:C1/U2") == ITEMS


@patch("fleetent.session.index.delete_batch")
def test_cleanup_expired_removes_todo_sibling(
    mock_delete_batch, tmp_path: Path, monkeypatch
) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    sess = tmp_path / "s1.json"
    sess.write_text('{"meta":{},"messages":[]}')
    os.utime(sess, (0, 0))  # expired (mtime epoch)
    mgr.write_todo("s1", ITEMS)

    removed = mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    assert "s1" in removed
    assert not sess.exists()
    assert not (tmp_path / "s1.todo").exists()


@patch("fleetent.session.index.delete_batch")
def test_cleanup_keeps_todo_of_unexpired_session(
    mock_delete_batch, tmp_path: Path, monkeypatch
) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    sess = tmp_path / "live.json"
    sess.write_text('{"meta":{},"messages":[]}')
    os.utime(sess, (1000, 1000))  # last-active at t=1000
    mgr.write_todo("live", ITEMS)

    mgr.cleanup_expired(ttl_seconds=100, _now=1050)  # 1050-1000=50 < 100 → not expired

    # Unexpired session keeps both its main file and its .todo sibling.
    assert sess.exists()
    assert (tmp_path / "live.todo").exists()
