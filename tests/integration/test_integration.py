"""End-to-end integration tests for the full IM message pipeline."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from alembic import command
from alembic.config import Config

import fleetent.governance.permission_gate as permission_gate
import fleetent.im_user_store as im_user_store
import fleetent.session_mgr as session_mgr
import fleetent.user_store as user_store


def _apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Redirect all data paths to tmp_path.

    Legacy stores share ``users.db`` via DB_PATH; the managed agent_store uses a
    separate Alembic-managed database so its schema does not collide with the
    legacy permission_gate ``approvals`` table.
    """
    db = tmp_path / "users.db"
    managed_db = tmp_path / "managed.db"
    monkeypatch.setattr(user_store, "DB_PATH", db)
    monkeypatch.setattr(im_user_store, "DB_PATH", db)
    monkeypatch.setattr(permission_gate, "DB_PATH", db)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{managed_db}")
    _apply_migrations(managed_db)
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    return tmp_path


async def test_full_slack_message_pipeline(isolated_db):
    """Mock Slack message → full pipeline → reply sent + session saved."""
    from fleetent.im_gateway.normalizer import NormalizedMessage, route

    reply_calls: list[str] = []

    async def fake_reply(text: str) -> None:
        reply_calls.append(text)

    # Mock agent_loop.run to return deterministic response and mutate messages in-place
    with patch("fleetent.agent_loop.run", new_callable=AsyncMock) as mock_run:

        async def fake_run(messages, **kwargs):
            messages.append({"role": "assistant", "content": "Hello from agent"})
            return "Hello from agent"

        mock_run.side_effect = fake_run

        msg = NormalizedMessage(
            platform="slack",
            session_id="user:U123",
            user_id="internal-user-1",
            text="Hello agent",
            attachments=[],
            reply_func=fake_reply,
        )
        await route(msg)

    # Verify agent was called
    mock_run.assert_called_once()
    call_kwargs = mock_run.call_args
    messages_arg = call_kwargs[1].get("messages") or call_kwargs[0][0]
    assert any(m.get("content") == "Hello agent" for m in messages_arg)

    # Verify reply was sent
    assert reply_calls == ["Hello from agent"]

    # Verify session was saved with system + user + assistant
    session_file = isolated_db / "sessions" / "user:U123.json"
    assert session_file.exists()
    saved = json.loads(session_file.read_text())["messages"]
    assert len(saved) == 3  # system message + user message + assistant response
    assert saved[-1]["role"] == "assistant"
    assert saved[-1]["content"] == "Hello from agent"


async def test_permission_gate_approved_tool_executes(isolated_db):
    """Tool with medium risk + approval → executes successfully."""
    import asyncio

    from fleetent.governance.permission_gate import PermissionGate

    gate = PermissionGate(medium_timeout=1.0, high_timeout=1.0)
    reply_func = AsyncMock()

    async def approve_it():
        await asyncio.sleep(0.05)
        await gate.resolve("test-appr-1", "approved", approver_user_id="user-1")

    asyncio.create_task(approve_it())

    result = await gate.request_approval(
        approval_id="test-appr-1",
        risk_level="medium",
        tool_name="send_email",
        tool_args={"to": "test@example.com"},
        requester_user_id="user-1",
        reply_func=reply_func,
    )

    assert result == "approved"

    # Verify approvals table has approved row
    conn = sqlite3.connect(isolated_db / "users.db")
    row = conn.execute("SELECT status FROM approvals WHERE id = ?", ("test-appr-1",)).fetchone()
    conn.close()
    assert row[0] == "approved"


async def test_tool_not_in_allowed_tools_raises_before_approval(isolated_db):
    """Tool not in agent's allowed_tools → PermissionError, no approval row created."""
    import fleetent.tool_registry as tr

    with pytest.raises(PermissionError, match="not permitted"):
        tr.dispatch("shell", {}, allowed_tools=["github__*"])

    # Verify no approval row was created (table may not exist — that's fine too)
    try:
        conn = sqlite3.connect(isolated_db / "users.db")
        count = conn.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]
        conn.close()
        assert count == 0
    except sqlite3.OperationalError:
        # approvals table not created — PermissionError fired before any DB access, which is correct
        pass


async def test_session_history_accumulates_across_messages(isolated_db):
    """Two messages to same session → history grows correctly."""
    from fleetent.im_gateway.normalizer import NormalizedMessage, route

    reply_calls: list[str] = []

    async def fake_reply(text: str) -> None:
        reply_calls.append(text)

    with patch("fleetent.agent_loop.run", new_callable=AsyncMock) as mock_run:

        async def fake_run(messages, **kwargs):
            messages.append({"role": "assistant", "content": "response"})
            return "response"

        mock_run.side_effect = fake_run

        for text in ["message one", "message two"]:
            msg = NormalizedMessage(
                platform="slack",
                session_id="user:U999",
                user_id="internal-user-2",
                text=text,
                attachments=[],
                reply_func=fake_reply,
            )
            await route(msg)

    # After two messages: system + user1 + assistant1 + user2 + assistant2 = 5 entries
    history = await session_mgr.load("user:U999")
    assert len(history) == 5
    assert history[1]["content"] == "message one"  # history[0] is system message
    assert history[3]["content"] == "message two"


def _capture_snapshot_run():
    """Return (patch_ctx, captured) where captured['snapshot'] holds the run snapshot."""
    captured: dict[str, object] = {}

    async def fake_run(messages, **kwargs):
        captured["snapshot"] = kwargs.get("snapshot")
        messages.append({"role": "assistant", "content": "ok"})
        return "ok"

    ctx = patch("fleetent.agent_loop.run", new_callable=AsyncMock)
    return ctx, captured, fake_run


async def _route_text(session_id, user_id, text):
    from fleetent.im_gateway.normalizer import NormalizedMessage, route

    async def fake_reply(_text: str) -> None:
        return None

    await route(
        NormalizedMessage(
            platform="slack",
            session_id=session_id,
            user_id=user_id,
            text=text,
            attachments=[],
            reply_func=fake_reply,
        )
    )


async def test_route_persists_agent_version_in_session_meta(isolated_db):
    """First route writes agent_id + agent_version_id into session meta."""
    import fleetent.agent_store as agent_store

    agent = agent_store.create_agent("billing", "Billing bot.", ["github__*"])
    agent_store.assign_user("internal-user-3", agent.id)

    ctx, captured, fake_run = _capture_snapshot_run()
    with ctx as mock_run:
        mock_run.side_effect = fake_run
        await _route_text("user:UMETA", "internal-user-3", "hi")

    meta = await session_mgr.load_meta("user:UMETA")
    assert meta["agent_id"] == agent.id
    assert meta["agent_version_id"] == agent.active_version_id
    snapshot = captured["snapshot"]
    assert snapshot is not None
    assert snapshot.version_id == agent.active_version_id


async def test_route_locks_session_to_version_across_activation(isolated_db):
    """A session stays pinned to its recorded version even after a new one activates."""
    import fleetent.agent_store as agent_store

    agent = agent_store.create_agent("ops", "Ops v1.", ["github__*"])
    agent_store.assign_user("internal-user-4", agent.id)
    v1_version_id = agent.active_version_id

    ctx, captured, fake_run = _capture_snapshot_run()
    with ctx as mock_run:
        mock_run.side_effect = fake_run
        await _route_text("user:ULOCK", "internal-user-4", "first")

    # Activate v2; the existing session must not follow.
    agent_store.create_version("ops", system_prompt="Ops v2.")

    ctx2, captured2, fake_run2 = _capture_snapshot_run()
    with ctx2 as mock_run2:
        mock_run2.side_effect = fake_run2
        await _route_text("user:ULOCK", "internal-user-4", "second")

    assert captured2["snapshot"].version_id == v1_version_id
    meta = await session_mgr.load_meta("user:ULOCK")
    assert meta["agent_version_id"] == v1_version_id


async def test_route_new_session_uses_current_active(isolated_db):
    """A brand-new session resolves the currently active version."""
    import fleetent.agent_store as agent_store

    agent = agent_store.create_agent("sales", "Sales v1.", ["github__*"])
    agent_store.assign_user("internal-user-5", agent.id)
    agent_store.create_version("sales", system_prompt="Sales v2.")
    active = agent_store.get_by_name("sales")

    ctx, captured, fake_run = _capture_snapshot_run()
    with ctx as mock_run:
        mock_run.side_effect = fake_run
        await _route_text("user:UNEW", "internal-user-5", "hello")

    assert captured["snapshot"].version_id == active.active_version_id
