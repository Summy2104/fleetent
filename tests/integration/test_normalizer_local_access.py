"""route() gates on the agent's local access config + approval store — zero platform DB."""

import contextlib

import pytest

import fleetent.im_gateway.access as access
from fleetent.agent_config import AgentAccess, AgentFile
from fleetent.im_gateway import normalizer
from fleetent.runtime import loop as agent_loop
from fleetent.session import manager as session_mgr


def _async(value):
    async def _coro():
        return value

    return _coro()


@pytest.fixture
def stub_loop(monkeypatch):
    """Short-circuit session + agent loop so we can detect 'proceeded to the loop'."""
    ran = {"loop": False}

    @contextlib.asynccontextmanager
    async def fake_lock(sid):
        yield

    async def fake_run(**kwargs):
        ran["loop"] = True
        return "ok"

    monkeypatch.setattr(session_mgr, "session_lock", fake_lock)
    monkeypatch.setattr(session_mgr, "load", lambda _sid: _async([]))
    monkeypatch.setattr(session_mgr, "save", lambda *a, **k: _async(None))
    monkeypatch.setattr(agent_loop, "run", fake_run)
    return ran


@pytest.fixture
def approvals(tmp_path, monkeypatch):
    path = tmp_path / "data" / "im_approvals.json"
    monkeypatch.setattr(access, "APPROVALS_PATH", path)
    return access.LocalApprovalStore(path)


def _agent(access_cfg):
    return AgentFile(name="a", version=1, access=access_cfg)


def _set_agent(monkeypatch, agent):
    monkeypatch.setattr(normalizer, "get_agent_for_context", lambda *a, **k: agent)


def _msg(replies, *, user_id="u1", channel_id="C1"):
    async def reply_func(text):
        replies.append(text)

    return normalizer.NormalizedMessage(
        platform="slack",
        owner_id="",
        session_id="s1",
        user_id=user_id,
        text="hi",
        attachments=[],
        reply_func=reply_func,
        channel_id=channel_id,
    )


async def test_allowed_user_proceeds(monkeypatch, stub_loop, approvals):
    _set_agent(monkeypatch, _agent(AgentAccess(allow_users=["u1"])))
    await normalizer.route(_msg([]))
    assert stub_loop["loop"] is True


async def test_locally_approved_user_proceeds(monkeypatch, stub_loop, approvals):
    approvals.approve("u1")
    _set_agent(monkeypatch, _agent(AgentAccess(require_approval=True)))
    await normalizer.route(_msg([]))
    assert stub_loop["loop"] is True


async def test_disallowed_user_with_require_approval_blocked_and_pending(
    monkeypatch, stub_loop, approvals
):
    _set_agent(monkeypatch, _agent(AgentAccess(require_approval=True)))
    replies = []
    await normalizer.route(_msg(replies))
    assert stub_loop["loop"] is False  # never reached the loop
    assert replies and replies[0] == normalizer._REJECTION_MSG
    assert "u1" in approvals.list_pending()  # recorded for later approval


async def test_channel_not_in_allow_channels_blocked(monkeypatch, stub_loop, approvals):
    _set_agent(monkeypatch, _agent(AgentAccess(allow_channels=["C_ok"], allow_users=["u1"])))
    replies = []
    await normalizer.route(_msg(replies, channel_id="C_bad"))
    assert stub_loop["loop"] is False
    assert replies and replies[0] == normalizer._REJECTION_MSG


async def test_empty_allow_channels_allows_any(monkeypatch, stub_loop, approvals):
    _set_agent(monkeypatch, _agent(AgentAccess(allow_users=["u1"])))
    await normalizer.route(_msg([], channel_id="C_anything"))
    assert stub_loop["loop"] is True


async def test_zero_db_proof_routing_decides_locally(monkeypatch, stub_loop, approvals):
    # Rig the platform allowlist/user-store to raise; routing must still decide.
    import fleetent.platform.im_gateway_management as platform_im
    import fleetent.user_store as user_store

    def boom(*a, **k):
        raise AssertionError("platform DB must not be read on the runtime path")

    monkeypatch.setattr(platform_im, "is_allowed", boom)
    monkeypatch.setattr(platform_im, "check_allowed_by_user_id", boom)
    monkeypatch.setattr(user_store, "_conn", boom)

    _set_agent(monkeypatch, _agent(AgentAccess(allow_users=["u1"])))
    await normalizer.route(_msg([]))
    assert stub_loop["loop"] is True
