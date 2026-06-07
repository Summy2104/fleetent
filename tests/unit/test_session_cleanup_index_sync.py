"""Unit tests: cleanup_expired and enforce_capacity sync deletions to session index."""

from __future__ import annotations

import os
from unittest.mock import patch


@patch("fleetent.session.index.delete_batch")
def test_cleanup_expired_calls_delete_batch_for_removed(mock_delete_batch, tmp_path, monkeypatch):
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    # Create an expired session file (mtime=0)
    p = tmp_path / "expired-sess.json"
    p.write_text('{"meta":{},"messages":[]}')
    os.utime(p, (0, 0))

    mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    mock_delete_batch.assert_called_once_with(["expired-sess"])


@patch("fleetent.session.index.delete_batch")
def test_cleanup_expired_no_delete_batch_when_nothing_removed(
    mock_delete_batch, tmp_path, monkeypatch
):
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    # No files → nothing removed
    mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    mock_delete_batch.assert_not_called()


@patch("fleetent.session.index.delete_batch")
def test_cleanup_expired_index_failure_does_not_raise(mock_delete_batch, tmp_path, monkeypatch):
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    p = tmp_path / "sess.json"
    p.write_text("{}")
    os.utime(p, (0, 0))

    mock_delete_batch.side_effect = RuntimeError("db locked")

    # Must not propagate the index error
    removed = mgr.cleanup_expired(ttl_seconds=1, _now=1e12)
    assert "sess" in removed  # file was still deleted


@patch("fleetent.session.index.delete_batch")
def test_enforce_capacity_calls_delete_batch_for_evicted(mock_delete_batch, tmp_path, monkeypatch):
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    for i in range(3):
        p = tmp_path / f"s{i}.json"
        p.write_text("{}")
        os.utime(p, (i, i))

    mgr.enforce_capacity(max_count=1)

    # 2 sessions evicted → delete_batch called with those 2 ids
    mock_delete_batch.assert_called_once()
    evicted = mock_delete_batch.call_args[0][0]
    assert len(evicted) == 2


@patch("fleetent.session.index.delete_batch")
def test_enforce_capacity_no_delete_batch_when_within_limits(
    mock_delete_batch, tmp_path, monkeypatch
):
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    p = tmp_path / "s.json"
    p.write_text("{}")

    mgr.enforce_capacity(max_count=10)

    mock_delete_batch.assert_not_called()
