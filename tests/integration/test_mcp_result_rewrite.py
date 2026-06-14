"""Integration: deterministic chokepoint rewrite of MCP result paths → /exchange + ledger.

A tool result containing a host absolute path inside the server's effective root is
rewritten to its `/exchange/<server_id>/<rel>` canonical form and the file is registered
in the artifacts ledger, attributed to the current run's scope_key (D0). Paths outside
the root are left untouched.
"""

from __future__ import annotations

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
    root = tmp_path / "exchange" / "gd" / "data"
    root.mkdir(parents=True)
    (root / "out").mkdir()
    (root / "out" / "report.xlsx").write_bytes(b"xlsx-bytes")
    artifact_exchange.register_server_root("gd", root)
    return root


def test_rewrite_replaces_in_root_path_and_registers(_exchange):
    root = _exchange
    text = f'{{"localPath": "{root}/out/report.xlsx", "ok": true}}'
    out = artifact_exchange.rewrite_and_register(
        "gd", text, scope_key="K1", session_id="S1", user_id="U1"
    )
    assert "/exchange/gd/out/report.xlsx" in out
    assert str(root) not in out  # the host path is gone
    arts = artifact_exchange.list_by_scope("K1")
    assert len(arts) == 1
    assert arts[0].rel_path == "out/report.xlsx"
    assert arts[0].scope_key == "K1"
    assert arts[0].session_id == "S1"  # audit column
    assert arts[0].filename == "report.xlsx"


def test_rewrite_leaves_out_of_root_paths_untouched(_exchange):
    out = artifact_exchange.rewrite_and_register("gd", '{"path": "/etc/passwd"}', scope_key="K1")
    assert out == '{"path": "/etc/passwd"}'
    assert artifact_exchange.list_by_scope("K1") == []


def test_rewrite_noop_without_scope_key_or_unregistered_server(_exchange):
    root = _exchange
    text = f'"{root}/out/report.xlsx"'
    # no scope_key → cannot attribute → leave text untouched, no registration
    assert artifact_exchange.rewrite_and_register("gd", text, scope_key=None) == text
    # unregistered server → untouched
    assert artifact_exchange.rewrite_and_register("nope", text, scope_key="K1") == text
    assert artifact_exchange.list_by_scope("K1") == []


def test_rewrite_idempotent_same_scope(_exchange):
    root = _exchange
    text = f'"{root}/out/report.xlsx"'
    artifact_exchange.rewrite_and_register("gd", text, scope_key="K1")
    artifact_exchange.rewrite_and_register("gd", text, scope_key="K1")
    assert len(artifact_exchange.list_by_scope("K1")) == 1  # no duplicate row


async def test_call_tool_applies_chokepoint_rewrite(_exchange, monkeypatch):
    """The chokepoint (_call_via_session via call_tool) rewrites + registers when a
    scope_key is threaded — covering both MCP dispatch paths' shared funnel."""
    import types

    import fleetent.integrations.mcp.client as mc
    from fleetent.integrations.mcp.client import HealthState, McpServerConfig

    root = _exchange
    server = McpServerConfig(id="gd", transport="stdio", command="x")
    server._health = HealthState.healthy
    monkeypatch.setattr(mc, "_server_registry", {(None, "gd"): server})

    result_text = f"exported to {root}/out/report.xlsx"

    class _Sess:
        async def call_tool(self, name, args):
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(type="text", text=result_text)],
                structuredContent=None,
                isError=False,
            )

    monkeypatch.setattr(mc, "_active_sessions", {(None, "gd"): _Sess()})

    out = await mc.call_tool("gd", "export", {}, scope=None, scope_key="K1", session_id="S1")
    assert "/exchange/gd/out/report.xlsx" in out
    assert str(root) not in out
    arts = artifact_exchange.list_by_scope("K1")
    assert len(arts) == 1 and arts[0].rel_path == "out/report.xlsx"


def test_diff_register_picks_up_unmentioned_new_file(_exchange):
    root = _exchange
    before = artifact_exchange.snapshot_products(root)
    (root / "out" / "extra.csv").write_text("data")  # server wrote it; result never names it
    newly = artifact_exchange.diff_register("gd", root, before, "K1", session_id="S1")
    assert "out/extra.csv" in newly
    assert "out/extra.csv" in {a.rel_path for a in artifact_exchange.list_by_scope("K1")}


def test_diff_register_skips_dotfiles_and_tmp(_exchange):
    root = _exchange
    before = artifact_exchange.snapshot_products(root)
    (root / ".hidden").write_text("x")
    (root / "scratch.tmp").write_text("x")
    assert artifact_exchange.diff_register("gd", root, before, "K1") == []


def test_diff_register_ignores_preexisting_unchanged(_exchange):
    root = _exchange  # already has out/report.xlsx
    before = artifact_exchange.snapshot_products(root)
    assert artifact_exchange.diff_register("gd", root, before, "K1") == []


def test_diff_register_noop_without_scope_key(_exchange):
    root = _exchange
    before = artifact_exchange.snapshot_products(root)
    (root / "out" / "extra.csv").write_text("data")
    assert artifact_exchange.diff_register("gd", root, before, None) == []
    assert artifact_exchange.list_by_scope("K1") == []


async def test_call_tool_diff_registers_unmentioned_product(_exchange, monkeypatch):
    """The call-window diff (§2.5) registers a product the result text never names."""
    import types

    import fleetent.integrations.mcp.client as mc
    from fleetent.integrations.mcp.client import HealthState, McpServerConfig

    root = _exchange
    server = McpServerConfig(id="gd", transport="stdio", command="x")
    server._health = HealthState.healthy
    monkeypatch.setattr(mc, "_server_registry", {(None, "gd"): server})

    class _Sess:
        async def call_tool(self, name, args):
            # The tool writes a file but its result text does NOT mention the path.
            (root / "out" / "silent.bin").write_bytes(b"x")
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(type="text", text="done")],
                structuredContent=None,
                isError=False,
            )

    monkeypatch.setattr(mc, "_active_sessions", {(None, "gd"): _Sess()})
    out = await mc.call_tool("gd", "gen", {}, scope=None, scope_key="K1", session_id="S1")
    assert out == "done"  # result text unchanged (no path to rewrite)
    assert "out/silent.bin" in {a.rel_path for a in artifact_exchange.list_by_scope("K1")}


async def test_call_tool_no_scope_key_is_byte_identical(_exchange, monkeypatch):
    """No scope_key (e.g. no run context) → legacy behavior: raw result, no registration."""
    import types

    import fleetent.integrations.mcp.client as mc
    from fleetent.integrations.mcp.client import HealthState, McpServerConfig

    root = _exchange
    server = McpServerConfig(id="gd", transport="stdio", command="x")
    server._health = HealthState.healthy
    monkeypatch.setattr(mc, "_server_registry", {(None, "gd"): server})
    result_text = f"exported to {root}/out/report.xlsx"

    class _Sess:
        async def call_tool(self, name, args):
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(type="text", text=result_text)],
                structuredContent=None,
                isError=False,
            )

    monkeypatch.setattr(mc, "_active_sessions", {(None, "gd"): _Sess()})
    out = await mc.call_tool("gd", "export", {}, scope=None)
    assert out == result_text  # untouched
    assert artifact_exchange.list_by_scope("K1") == []
