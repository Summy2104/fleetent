"""Integration tests: session_start + session_end hooks in normalizer.route() (P4)."""

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
            supports_dm=True,
            slack=SlackConnector(
                bot_token_env="BOT",
                app_token_env="APP",
                access=ConnectorAccess(allow_users=["u1"]),
            ),
        ),
        hooks_enabled=True,
    )
    monkeypatch.setattr(norm, "get_agent_for_context", lambda *a, **k: agent)
    monkeypatch.setattr(al, "run", AsyncMock(return_value="session reply"))
    return {"agent": agent, "norm": norm}


def _msg() -> tuple[NormalizedMessage, list[str]]:
    replies: list[str] = []

    async def reply_func(t: str) -> None:
        replies.append(t)

    return (
        NormalizedMessage(
            platform="slack",
            session_id="u1:s1",
            user_id="u1",
            text="hello",
            attachments=[],
            reply_func=reply_func,
        ),
        replies,
    )


async def test_session_start_inject_context(_mock_env):
    @hooks.hook("session_start")
    def inject(ctx):
        return HookResult(inject_context="[COMPLIANCE CONTEXT]")

    captured: list = []

    async def capture_run(**kw):
        captured.extend(kw.get("messages", []))
        return "ok"

    al.run.side_effect = capture_run
    msg, _ = _msg()
    await route(msg)
    injected = [m for m in captured if "[COMPLIANCE CONTEXT]" in str(m.get("content", ""))]
    assert len(injected) >= 1


async def test_session_end_called_with_reply(_mock_env):
    observed: list[dict] = []

    @hooks.hook("session_end")
    def audit(ctx):
        observed.append(dict(ctx.payload))
        return None

    al.run.return_value = "final reply"
    msg, _ = _msg()
    await route(msg)
    assert len(observed) >= 1
    assert observed[-1]["reply"] == "final reply"


async def test_session_hooks_disabled_no_effect(_mock_env):
    import fleetent.im_gateway.normalizer as norm
    from fleetent.agent_config import AgentFile, default_models

    # Override with hooks_enabled=False
    agent_off = AgentFile(
        name="test-agent",
        version=1,
        models=default_models(),
        connectors=AgentConnectors(
            supports_dm=True,
            slack=SlackConnector(
                bot_token_env="BOT",
                app_token_env="APP",
                access=ConnectorAccess(allow_users=["u1"]),
            ),
        ),
        hooks_enabled=False,
    )
    norm.get_agent_for_context = lambda *a, **k: agent_off

    called: list[bool] = []

    @hooks.hook("session_start")
    def track(ctx):
        called.append(True)
        return None

    msg, _ = _msg()
    await route(msg)
    assert called == []
