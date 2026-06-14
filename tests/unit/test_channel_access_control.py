"""Tests for channel-access-control: allow_all_users flag and channel-grants-access logic."""

import contextlib
from unittest.mock import AsyncMock

import pytest

from fleetent.agent_config import (
    AgentFile,
    ImAccess,
    ImBinding,
    SlackBinding,
    TelegramBinding,
    default_models,
)

# ── Task 1.1: ImAccess.allow_all_users 字段默认 false ─────────────────


def test_connector_access_allow_all_users_default_false():
    access = ImAccess()
    assert access.allow_all_users is False


def test_connector_access_allow_all_users_can_be_true():
    access = ImAccess(allow_all_users=True)
    assert access.allow_all_users is True


def test_connector_access_allow_all_users_in_slack_connector():
    conn = SlackBinding(
        bot_token_env="BOT",
        app_token_env="APP",
        access=ImAccess(allow_all_users=True),
    )
    assert conn.access.allow_all_users is True


def test_connector_access_allow_all_users_in_telegram_connector():
    conn = TelegramBinding(
        bot_token_env="BOT",
        access=ImAccess(allow_all_users=True),
    )
    assert conn.access.allow_all_users is True


# ── Task 2.1-2.4: normalizer.route() 门控短路逻辑 ────────────────────────────

_MODELS = default_models()


def _agent_with_slack_access(
    allow_groups: list[str] | None = None,
    allow_users: list[str] | None = None,
    allow_all_users: bool = False,
    require_approval: bool = True,
    supports_dm: bool = False,
    supports_groups: bool = False,
) -> AgentFile:
    access = ImAccess(
        allow_groups=allow_groups or [],
        allow_users=allow_users or [],
        allow_all_users=allow_all_users,
        require_approval=require_approval,
    )
    return AgentFile(
        name="test",
        version=1,
        models=_MODELS,
        im=ImBinding(
            supports_dm=supports_dm,
            supports_groups=supports_groups,
            slack=SlackBinding(bot_token_env="BOT", app_token_env="APP", access=access),
        ),
    )


def _msg(channel_id: str = "C1", user_id: str = "U_unknown", platform: str = "slack"):
    from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext

    replies: list[str] = []

    async def reply_func(text: str) -> None:
        replies.append(text)

    return NormalizedMessage(
        platform=platform,
        session_id=f"user:{user_id}",
        user_id=user_id,
        text="hello",
        attachments=[],
        reply_func=reply_func,
        channel_id=channel_id,
        agent_name="test",
        session_context=SessionContext(
            platform=platform,
            sender_id=user_id,
            chat_type="dm" if channel_id.startswith("D") else "channel",
            channel_name=channel_id,
        ),
    ), replies


async def _route_with_agent(
    agent: AgentFile, channel_id: str, user_id: str, platform: str = "slack"
):
    """Route a message through normalizer.route() with the given agent monkeypatched."""
    from fleetent import agent_config
    from fleetent.agent_config import AgentConfigIndex
    from fleetent.im_gateway import access as access_mod

    msg, replies = _msg(channel_id=channel_id, user_id=user_id, platform=platform)

    fake_index = AgentConfigIndex(agents={"test": agent}, default="test")

    # Patch agent lookup and approval store; also short-circuit the agent loop
    import fleetent.im_gateway.normalizer as norm_mod
    from fleetent.runtime import loop as agent_loop
    from fleetent.session import manager as session_mgr

    async def fake_loop(**kwargs):
        return "ok"

    @contextlib.asynccontextmanager
    async def fake_lock(sid):
        yield

    import unittest.mock as mock

    with (
        mock.patch.object(agent_config, "_index", fake_index),
        mock.patch.object(access_mod, "APPROVALS_PATH", "/tmp/test_approvals_nonexistent.json"),
        mock.patch.object(session_mgr, "session_lock", fake_lock),
        mock.patch.object(session_mgr, "load", AsyncMock(return_value=[])),
        mock.patch.object(session_mgr, "load_meta", AsyncMock(return_value={})),
        mock.patch.object(session_mgr, "save", AsyncMock()),
        mock.patch.object(session_mgr, "is_resume_pending", return_value=False),
        mock.patch.object(agent_loop, "run", AsyncMock(return_value="ok")),
    ):
        await norm_mod.route(msg)

    return replies


# Task 2.1: 频道在 allow_groups 中 → 跳过用户门控
@pytest.mark.asyncio
async def test_user_in_listed_channel_bypasses_user_gate(tmp_path):
    agent = _agent_with_slack_access(allow_groups=["C1"], allow_users=[], supports_groups=True)
    replies = await _route_with_agent(agent, channel_id="C1", user_id="U_unknown")
    # Should NOT get rejection message — message proceeds to loop
    assert not any("权限" in r or "审批" in r for r in replies)


# Task 2.2: allow_groups 为空 → 用户门控不跳过
@pytest.mark.asyncio
async def test_empty_allow_groups_does_not_skip_user_gate(tmp_path):
    agent = _agent_with_slack_access(allow_groups=[], allow_users=[], supports_groups=True)
    replies = await _route_with_agent(agent, channel_id="C1", user_id="U_unknown")
    # Should get rejection message — user gate active
    assert any("权限" in r or "审批" in r for r in replies)


# Task 2.3: allow_all_users=True → 跳过用户门控
@pytest.mark.asyncio
async def test_allow_all_users_true_skips_user_gate(tmp_path):
    agent = _agent_with_slack_access(allow_all_users=True, supports_dm=True)
    replies = await _route_with_agent(agent, channel_id="D_dm", user_id="U_unknown")
    # Should NOT get rejection
    assert not any("权限" in r or "审批" in r for r in replies)


# Task 2.4: allow_all_users=False（默认）→ 用户门控保持
@pytest.mark.asyncio
async def test_allow_all_users_false_keeps_user_gate(tmp_path):
    agent = _agent_with_slack_access(allow_all_users=False, allow_users=[], supports_dm=True)
    replies = await _route_with_agent(agent, channel_id="C1", user_id="U_unknown")
    assert any("权限" in r or "审批" in r for r in replies)
