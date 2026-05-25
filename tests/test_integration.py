"""End-to-end integration tests for the full IM message pipeline."""
from __future__ import annotations

import json
import sqlite3
from unittest.mock import AsyncMock, patch

import pytest

import fleetent.agent_store as agent_store
import fleetent.im_user_store as im_user_store
import fleetent.permission_gate as permission_gate
import fleetent.session_mgr as session_mgr
import fleetent.user_store as user_store


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Redirect all data paths to tmp_path."""
    db = tmp_path / "users.db"
    monkeypatch.setattr(user_store, "DB_PATH", db)
    monkeypatch.setattr(im_user_store, "DB_PATH", db)
    monkeypatch.setattr(agent_store, "DB_PATH", db)
    monkeypatch.setattr(permission_gate, "DB_PATH", db)
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
    saved = json.loads(session_file.read_text())
    assert len(saved) == 3  # system message + user message + assistant response
    assert saved[-1]["role"] == "assistant"
    assert saved[-1]["content"] == "Hello from agent"


async def test_permission_gate_approved_tool_executes(isolated_db):
    """Tool with medium risk + approval → executes successfully."""
    import asyncio

    from fleetent.permission_gate import PermissionGate

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
    row = conn.execute(
        "SELECT status FROM approvals WHERE id = ?", ("test-appr-1",)
    ).fetchone()
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
    assert history[1]["content"] == "message one"   # history[0] is system message
    assert history[3]["content"] == "message two"
