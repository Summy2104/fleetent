"""End-to-end integration tests for the full IM message pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import fleetent.governance.approval_store as approval_store
import fleetent.governance.tool_auto_approvals_store as tool_auto_approvals_store
import fleetent.im_gateway.outbound as outbound_mod
import fleetent.session.manager as session_mgr
from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
from fleetent.schema_migrations import migrate
from tests.integration._migration_template import apply_migrations as _apply_migrations


def _bind_default_agent(tmp_path: Path, user_id: str, monkeypatch) -> None:
    """Deploy a single home agent allowing ``user_id`` (forced default — bindings were
    removed from AgentFile; the IM gate lives on the connector declaration)."""
    import yaml

    import fleetent.agent_config as agent_config

    d = tmp_path / "agents" / "default"
    d.mkdir(parents=True, exist_ok=True)
    doc = {
        "name": "default",
        "version": 1,
        "models": agent_config.default_models().model_dump(mode="json"),
        "connectors": {
            "slack": {
                "bot_token_env": "TEST_BOT_TOKEN",
                "app_token_env": "TEST_APP_TOKEN",
                "access": {"allow_users": [user_id]},
            }
        },
    }
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    monkeypatch.delenv("FLEETENT_AGENTS_DIR", raising=False)
    agent_config.scan()


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Redirect all data paths to tmp_path.

    approval_store (agent-side) uses a separate SQLite in tmp_path; the managed
    agent_store uses a separate Alembic-managed database so schemas do not collide.
    """
    managed_db = tmp_path / "managed.db"
    approval_db = tmp_path / "agent.db"
    state_db = SQLiteDatabase(path=approval_db)
    migrate(state_db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(approval_store, "_state_db", state_db)
    monkeypatch.setattr(tool_auto_approvals_store, "_state_db", state_db)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{managed_db}")
    _apply_migrations(managed_db)
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")
    return tmp_path


async def test_full_slack_message_pipeline(isolated_db, monkeypatch):
    """Mock Slack message → full pipeline → reply sent + session saved."""
    from fleetent.im_gateway.normalizer import NormalizedMessage, route

    _bind_default_agent(isolated_db, "internal-user-1", monkeypatch)

    reply_calls: list[str] = []

    async def fake_reply(text: str) -> None:
        reply_calls.append(text)

    # Mock agent_loop.run to return deterministic response and mutate messages in-place
    with patch("fleetent.runtime.loop.run", new_callable=AsyncMock) as mock_run:

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


async def test_permission_gate_pending_then_resolve_finalizes(isolated_db, monkeypatch):
    """Medium risk + routing → request registers pending; resolve finalizes the row.

    Suspend model (approval-suspend-resume): request_approval no longer blocks; it
    returns "pending" and the row reads pending until an out-of-band resolve.
    """
    from fleetent.agent_config import ApprovalRouting
    from fleetent.governance.permission_gate import PermissionGate

    # Mock outbound so DM send succeeds without real Slack.
    monkeypatch.setattr(outbound_mod, "send_to", AsyncMock(return_value=True))
    monkeypatch.setattr(outbound_mod, "is_reachable", AsyncMock(return_value=True))

    gate = PermissionGate()
    routing = ApprovalRouting(
        by_risk={"medium": {"approvers": ["slack:U_APPROVER"], "policy": "any"}}
    )

    result = await gate.request_approval(
        approval_id="test-appr-1",
        risk_level="medium",
        tool_name="send_email",
        tool_args={"to": "test@example.com"},
        requester_user_id="user-1",
        reply_func=AsyncMock(),
        session_id="test-session",
        approval_routing=routing,
        outbound_connectors={"slack": AsyncMock()},
    )
    assert result == "pending"

    def _status() -> str:
        row = approval_store.get_approval("test-appr-1")
        assert row is not None
        return str(row["status"])

    assert _status() == "pending"
    assert await gate.resolve("test-appr-1", "approved", approver_user_id="U_APPROVER") is True
    assert _status() == "approved"


async def test_tool_not_in_allowed_tools_raises_before_approval(isolated_db):
    """Tool not in agent's allowed_tools → PermissionError, no approval row created."""
    import fleetent.tools.registry as tr

    with pytest.raises(PermissionError, match="not permitted"):
        tr.dispatch("shell", {}, allowed_tools=["github__*"])

    assert approval_store.list_approvals() == []


async def test_session_history_accumulates_across_messages(isolated_db, monkeypatch):
    """Two messages to same session → history grows correctly."""
    from fleetent.im_gateway.normalizer import NormalizedMessage, route

    _bind_default_agent(isolated_db, "internal-user-2", monkeypatch)

    reply_calls: list[str] = []

    async def fake_reply(text: str) -> None:
        reply_calls.append(text)

    with patch("fleetent.runtime.loop.run", new_callable=AsyncMock) as mock_run:

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
