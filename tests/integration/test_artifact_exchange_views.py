"""Integration: scope-attribution hard-link views (§4.1/4.2).

On registration an artifact is hard-linked into `<views_root>/<scope_key>/<server_id>/<rel>`
so the sandbox can read-only mount exactly the current run's scope view. Re-registration
(inode change) refreshes the link; cross-scope views are physically separate.
"""

from __future__ import annotations

import os

import pytest

from fleetent import artifact_exchange
from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.schema_migrations import migrate


@pytest.fixture
def _exchange(tmp_path, monkeypatch):
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, MIGRATIONS)
    monkeypatch.setattr(artifact_exchange, "_state_db", db)
    monkeypatch.setattr(artifact_exchange, "_server_roots", {})
    monkeypatch.setattr(artifact_exchange, "_views_root", None)
    monkeypatch.setattr(artifact_exchange, "_staging_degraded_servers", set())
    root = tmp_path / "exchange" / "gd" / "data"
    root.mkdir(parents=True)
    (root / "report.txt").write_text("hello")
    artifact_exchange.register_server_root("gd", root)
    views = tmp_path / "exchange" / ".views"
    artifact_exchange.set_views_root(views)
    return root, views


def test_register_hardlinks_into_scope_view(_exchange):
    root, views = _exchange
    artifact_exchange.register(server_id="gd", rel_path="report.txt", scope_key="K1")
    link = views / "K1" / "gd" / "report.txt"
    assert link.is_file()
    # same inode → a hard link, not a copy
    assert link.stat().st_ino == (root / "report.txt").stat().st_ino


def test_cross_scope_views_physically_separate(_exchange):
    _, views = _exchange
    artifact_exchange.register(server_id="gd", rel_path="report.txt", scope_key="K1")
    assert (views / "K1" / "gd" / "report.txt").is_file()
    assert not (views / "K2").exists()  # K2 never registered → no view


def test_reregister_refreshes_link_on_inode_change(_exchange):
    root, views = _exchange
    artifact_exchange.register(server_id="gd", rel_path="report.txt", scope_key="K1")
    link = views / "K1" / "gd" / "report.txt"
    first_ino = link.stat().st_ino
    # server replaces the file (new inode), then re-registers
    (root / "report.txt").unlink()
    (root / "report.txt").write_text("new content")
    artifact_exchange.register(server_id="gd", rel_path="report.txt", scope_key="K1")
    assert link.stat().st_ino == (root / "report.txt").stat().st_ino
    assert link.stat().st_ino != first_ino


def test_view_link_noop_without_views_root(_exchange, monkeypatch):
    _, views = _exchange
    monkeypatch.setattr(artifact_exchange, "_views_root", None)
    artifact_exchange.register(server_id="gd", rel_path="report.txt", scope_key="K1")
    assert not (views / "K1").exists()  # no views_root → no link, no crash


def test_cross_filesystem_marks_staging_degrade(_exchange, monkeypatch):
    root, views = _exchange

    def _boom(src, dst):  # simulate EXDEV (cross-filesystem)
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(os, "link", _boom)
    artifact_exchange.register(server_id="gd", rel_path="report.txt", scope_key="K1")
    assert "gd" in artifact_exchange._staging_degraded_servers  # degrade flagged, no crash
