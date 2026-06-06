"""Unit tests: compaction checkpoint functions in session/manager.py."""

from __future__ import annotations

import json
from pathlib import Path

# ── write_compaction_checkpoint ───────────────────────────────────────────────


def test_write_compaction_checkpoint_creates_file(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    messages = [{"role": "user", "content": "hello"}]

    mgr.write_compaction_checkpoint("sess-1", messages)

    checkpoint = tmp_path / "sess-1.pre-compact.json"
    assert checkpoint.exists()
    data = json.loads(checkpoint.read_text())
    assert data["messages"] == messages
    assert "compacted_at" in data


def test_write_compaction_checkpoint_overwrites_existing(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    mgr.write_compaction_checkpoint("sess-2", [{"role": "user", "content": "old"}])
    mgr.write_compaction_checkpoint("sess-2", [{"role": "user", "content": "new"}])

    data = json.loads((tmp_path / "sess-2.pre-compact.json").read_text())
    assert data["messages"][0]["content"] == "new"


def test_write_compaction_checkpoint_slash_session_id(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    messages = [{"role": "user", "content": "hi"}]

    mgr.write_compaction_checkpoint("platform/channel/user", messages)

    checkpoint = tmp_path / "platform" / "channel" / "user.pre-compact.json"
    assert checkpoint.exists()
    assert json.loads(checkpoint.read_text())["messages"] == messages


# ── delete_compaction_checkpoint ──────────────────────────────────────────────


def test_delete_compaction_checkpoint_removes_file(tmp_path: Path, monkeypatch) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    mgr.write_compaction_checkpoint("sess-3", [])
    assert (tmp_path / "sess-3.pre-compact.json").exists()

    mgr.delete_compaction_checkpoint("sess-3")

    assert not (tmp_path / "sess-3.pre-compact.json").exists()


def test_delete_compaction_checkpoint_nonexistent_is_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)
    # Should not raise
    mgr.delete_compaction_checkpoint("no-such-session")


# ── session package exports ───────────────────────────────────────────────────


def test_session_package_exports_checkpoint_functions() -> None:
    from fleetent import session as session_pkg

    assert hasattr(session_pkg, "write_compaction_checkpoint")
    assert hasattr(session_pkg, "delete_compaction_checkpoint")


# ── cleanup_expired pre-compact integration ───────────────────────────────────


def test_cleanup_expired_skips_pre_compact_files(tmp_path: Path, monkeypatch) -> None:
    """cleanup_expired must NOT treat .pre-compact.json as a standalone session."""
    import os
    from unittest.mock import patch

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    # Only create a .pre-compact.json, no corresponding .json
    p = tmp_path / "orphan.pre-compact.json"
    p.write_text('{"messages": []}')
    os.utime(p, (0, 0))  # old mtime

    with patch("fleetent.session.index.delete_batch"):
        removed = mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    assert removed == []  # .pre-compact.json was NOT treated as a session
    assert p.exists()  # file left untouched


def test_cleanup_expired_deletes_pre_compact_after_main(tmp_path: Path, monkeypatch) -> None:
    """cleanup_expired deletes the .pre-compact.json when main file is expired."""
    import os
    from unittest.mock import patch

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    # Create both files, both old
    main = tmp_path / "my-sess.json"
    main.write_text('{"meta": {}, "messages": []}')
    os.utime(main, (0, 0))

    backup = tmp_path / "my-sess.pre-compact.json"
    backup.write_text('{"messages": []}')
    os.utime(backup, (0, 0))

    with patch("fleetent.session.index.delete_batch"):
        removed = mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    assert "my-sess" in removed
    assert not main.exists()
    assert not backup.exists()  # backup also deleted


def test_cleanup_expired_no_error_when_no_pre_compact(tmp_path: Path, monkeypatch) -> None:
    """cleanup_expired works fine when there's no .pre-compact.json to delete."""
    import os
    from unittest.mock import patch

    import fleetent.session.manager as mgr

    monkeypatch.setattr(mgr, "SESSIONS_DIR", tmp_path)

    main = tmp_path / "solo-sess.json"
    main.write_text("{}")
    os.utime(main, (0, 0))

    with patch("fleetent.session.index.delete_batch"):
        removed = mgr.cleanup_expired(ttl_seconds=1, _now=1e12)

    assert "solo-sess" in removed
    assert not main.exists()
