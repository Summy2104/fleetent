"""Integration tests: on_user_input hook in normalizer.route() (P3)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import fleetent.runtime.hooks as hooks
import fleetent.runtime.loop as al
from fleetent.agent_config import (
    AgentConnectors,
    AgentFile,
    ConnectorAccess,
    SlackConnector,
    default_models,
)
from fleetent.im_gateway.normalizer import NormalizedMessage, route
from fleetent.runtime.hooks import HookResult


@pytest.fixture(autouse=True)
def _reset():
    hooks.reset()
    yield
    hooks.reset()


@pytest.fixture
def _mock_env(monkeypatch):
    import fleetent.im_gateway.normalizer as norm
    import fleetent.im_user_store as ius
    import fleetent.session.manager as sm
    import fleetent.skills.registry as sr

    monkeypatch.setattr(sm, "load", AsyncMock(return_value=[]))
    monkeypatch.setattr(sm, "load_meta", AsyncMock(return_value={}))
    monkeypatch.setattr(sm, "save", AsyncMock())
    monkeypatch.setattr(sr, "match", lambda text: None)
    monkeypatch.setattr(ius, "check_allowed_by_user_id", lambda user_id: True)

    agent = AgentFile(
        name="test-agent",
        version=1,
        models=default_models(),
        connectors=AgentConnectors(
            slack=SlackConnector(
                bot_token_env="BOT",
                app_token_env="APP",
                access=ConnectorAccess(allow_users=["u1"]),
            )
        ),
        hooks_enabled=True,
    )
    monkeypatch.setattr(norm, "get_agent_for_context", lambda *a, **k: agent)
    monkeypatch.setattr(al, "run", AsyncMock(return_value="agent reply"))
    return {"agent": agent, "norm": norm}


def _msg(text: str = "hello") -> tuple[NormalizedMessage, list[str]]:
    replies: list[str] = []

    async def reply_func(t: str) -> None:
        replies.append(t)

    return (
        NormalizedMessage(
            platform="slack",
            session_id="u1:session1",
            user_id="u1",
            text=text,
            attachments=[],
            reply_func=reply_func,
        ),
        replies,
    )


async def test_normalizer_on_user_input_deny_blocks_run(_mock_env):
    @hooks.hook("on_user_input")
    def block(ctx):
        return HookResult(decision="deny", reason="spam")

    msg, replies = _msg("spam message")
    await route(msg)
    assert al.run.call_count == 0
    assert any("spam" in r or "⛔" in r for r in replies)


async def test_normalizer_on_user_input_modified_content(_mock_env):
    @hooks.hook("on_user_input")
    def sanitize(ctx):
        return HookResult(modified_content="[SAFE]")

    captured_history: list = []

    async def capture_run(**kw):
        captured_history.extend(kw.get("messages", []))
        return "ok"

    al.run.side_effect = capture_run

    msg, _ = _msg("original text")
    await route(msg)
    user_msgs = [m for m in captured_history if m.get("role") == "user"]
    contents = [m.get("content", "") for m in user_msgs]
    assert any("[SAFE]" in c for c in contents)
    assert not any("original text" in c for c in contents)
