"""Unit tests: two-layer (file + asyncio) session lock for cross-process safety."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


async def test_session_lock_creates_lock_file(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    async with mgr.session_lock("sess-1"):
        # Lock file should exist while held
        assert (tmp_path / "sess-1.lock").exists()


async def test_session_lock_slash_session_id_creates_subdir_lock(
    tmp_path: Path, monkeypatch
) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    async with mgr.session_lock("slack:C1/U2"):
        assert (tmp_path / "slack:C1" / "U2.lock").exists()


async def test_session_lock_uses_flock_lock_and_unlock(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mgr, "_flock_available", True)

    calls = []
    fake_fcntl = MagicMock()
    fake_fcntl.LOCK_EX = 2
    fake_fcntl.LOCK_UN = 8
    fake_fcntl.flock = lambda fd, op: calls.append(op)

    monkeypatch.setattr(mgr, "fcntl", fake_fcntl)

    async with mgr.session_lock("sess-2"):
        pass

    assert 2 in calls  # LOCK_EX acquired
    assert 8 in calls  # LOCK_UN released


async def test_session_lock_uses_to_thread_for_flock(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mgr, "_flock_available", True)

    fake_fcntl = MagicMock()
    fake_fcntl.LOCK_EX = 2
    fake_fcntl.LOCK_UN = 8
    monkeypatch.setattr(mgr, "fcntl", fake_fcntl)

    to_thread_called = []
    real_to_thread = asyncio.to_thread

    async def spy_to_thread(fn, *args, **kw):
        to_thread_called.append(fn)
        return await real_to_thread(fn, *args, **kw)

    monkeypatch.setattr(asyncio, "to_thread", spy_to_thread)

    async with mgr.session_lock("sess-3"):
        pass

    assert to_thread_called  # flock acquisition went through to_thread


async def test_session_lock_degrades_without_fcntl(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(mgr, "_flock_available", False)

    # Should work fine with only asyncio.Lock, no lock file required
    async with mgr.session_lock("sess-4"):
        pass  # no exception


def test_lock_file_not_in_scan_sessions(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    (tmp_path / "real-sess.json").write_text('{"meta":{},"messages":[]}')
    (tmp_path / "real-sess.lock").write_text("")

    ids = mgr.list_session_ids()
    assert "real-sess" in ids
    assert "real-sess.lock" not in ids
    assert not any(".lock" in sid for sid in ids)


def test_lock_file_not_deleted_by_cleanup(tmp_path: Path, monkeypatch) -> None:
    import os

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    lock = tmp_path / "old.lock"
    lock.write_text("")
    os.utime(lock, (0, 0))  # ancient mtime

    with patch("fleetent.session.index.delete_batch"):
        removed = mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    assert "old" not in removed  # .lock not treated as session
    assert lock.exists()  # not deleted
