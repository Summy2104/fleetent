"""Integration: file tools resolve the /exchange second root with attribution (§3).

A file tool path may be a /workspace-relative path OR an `/exchange/<server_id>/<rel>`
canonical path; the latter resolves through artifact_exchange with the run's scope_key
(own-scope allowed, cross-scope / unregistered rejected). /exchange artifacts are host
files, read directly regardless of the workspace backend.
"""

from __future__ import annotations

import pytest

from fleetent import artifact_exchange
from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.schema_migrations import migrate
from fleetent.tools import file_tools
from fleetent.tools.registry import ToolContext


@pytest.fixture
def _exchange(tmp_path, monkeypatch):
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, MIGRATIONS)
    monkeypatch.setattr(artifact_exchange, "_state_db", db)
    monkeypatch.setattr(artifact_exchange, "_server_roots", {})
    root = tmp_path / "exchange" / "gd" / "data"
    root.mkdir(parents=True)
    (root / "report.txt").write_text("line1\nline2\n")
    artifact_exchange.register_server_root("gd", root)
    return root


async def test_read_file_resolves_own_scope_exchange_artifact(_exchange):
    artifact_exchange.register(
        server_id="gd", rel_path="report.txt", scope_key="K1", session_id="S1"
    )
    ctx = ToolContext(session_id="S1", scope_key="K1")
    out = await file_tools.read_file("/exchange/gd/report.txt", tool_context=ctx)
    assert "line1" in out and "line2" in out


async def test_read_file_rejects_cross_scope_exchange_artifact(_exchange):
    # Artifact owned by another scope; this run is K2 → attribution fails, no read.
    artifact_exchange.register(
        server_id="gd", rel_path="report.txt", scope_key="K1", session_id="S1"
    )
    ctx = ToolContext(session_id="S2", scope_key="K2")
    out = await file_tools.read_file("/exchange/gd/report.txt", tool_context=ctx)
    assert "error" in out.lower()
    assert "line1" not in out


async def test_read_file_rejects_unregistered_exchange_path(_exchange):
    ctx = ToolContext(session_id="S1", scope_key="K1")
    out = await file_tools.read_file("/exchange/gd/report.txt", tool_context=ctx)  # not registered
    assert "error" in out.lower()


async def test_exchange_path_detection():
    assert file_tools._is_exchange_path("/exchange/gd/a.txt") is True
    assert file_tools._is_exchange_path("sub/a.txt") is False
    assert file_tools._is_exchange_path("/workspace/a.txt") is False
