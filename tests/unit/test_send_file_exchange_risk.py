"""Unit: send_file callable risk truth table (§6.1, D6/D7).

No-approval (low) iff the recipient is harness-fixed (always for send_file) ∧ the
conversation is a DM ∧ the file is owned by the current run's scope ∧ an interactive
session_context exists. Any miss → escalate to medium approval (replacing the old
fail-closed decline). session_context=None stays fail-closed (handled in the body).
"""

from __future__ import annotations

import types

import pytest

from fleetent import artifact_exchange
from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.schema_migrations import migrate
from fleetent.tools import builtin_tools
from fleetent.tools.registry import ToolContext


def _ctx(chat_type: str | None, scope_key: str | None = "K1"):
    sc = None if chat_type is None else types.SimpleNamespace(chat_type=chat_type, platform="slack")
    return ToolContext(session_id="S1", scope_key=scope_key, session_context=sc)


@pytest.fixture
def _exchange(tmp_path, monkeypatch):
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, MIGRATIONS)
    monkeypatch.setattr(artifact_exchange, "_state_db", db)
    monkeypatch.setattr(artifact_exchange, "_server_roots", {})
    monkeypatch.setattr(artifact_exchange, "_views_root", None)
    root = tmp_path / "exchange" / "gd" / "data"
    root.mkdir(parents=True)
    (root / "r.txt").write_text("x")
    artifact_exchange.register_server_root("gd", root)
    return root


def test_risk_dm_workspace_relative_is_low(_exchange):
    assert builtin_tools._send_file_risk({"path": "out.csv"}, _ctx("dm")) == "low"


def test_risk_dm_own_scope_exchange_is_low(_exchange):
    artifact_exchange.register(server_id="gd", rel_path="r.txt", scope_key="K1")
    assert builtin_tools._send_file_risk({"path": "/exchange/gd/r.txt"}, _ctx("dm", "K1")) == "low"


def test_risk_dm_cross_scope_exchange_is_medium(_exchange):
    artifact_exchange.register(server_id="gd", rel_path="r.txt", scope_key="K1")
    # current run is K2 → cross-scope → must escalate
    assert (
        builtin_tools._send_file_risk({"path": "/exchange/gd/r.txt"}, _ctx("dm", "K2")) == "medium"
    )


def test_risk_channel_is_medium(_exchange):
    assert builtin_tools._send_file_risk({"path": "out.csv"}, _ctx("channel")) == "medium"


def test_risk_no_session_context_is_medium(_exchange):
    assert builtin_tools._send_file_risk({"path": "out.csv"}, _ctx(None)) == "medium"


def test_risk_unregistered_exchange_is_medium(_exchange):
    # path not in ledger → cannot confirm own-scope → escalate
    assert (
        builtin_tools._send_file_risk({"path": "/exchange/gd/nope.txt"}, _ctx("dm", "K1"))
        == "medium"
    )
