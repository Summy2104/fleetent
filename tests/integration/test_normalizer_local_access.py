"""route() gates on the agent's local access config + approval store — zero platform DB."""

import contextlib

import pytest

import fleetent.im_gateway.access as access
from fleetent.agent_config import (
    AgentFile,
    ImAccess,
    ImBinding,
    SlackBinding,
    default_models,
)
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


def _agent(
    access_cfg: ImAccess,
    *,
    supports_dm: bool = False,
    supports_groups: bool = False,
):
    return AgentFile(
        name="a",
        version=1,
        models=default_models(),
        im=ImBinding(
            supports_dm=supports_dm,
            supports_groups=supports_groups,
            slack=SlackBinding(
                bot_token_env="BOT",
                app_token_env="APP",
                access=access_cfg,
            ),
        ),
    )


def _set_agent(monkeypatch, agent):
    monkeypatch.setattr(normalizer, "get_agent_for_context", lambda *a, **k: agent)


def _msg(replies, *, user_id="u1", channel_id="C1", chat_type="dm"):
    async def reply_func(text):
        replies.append(text)

    return normalizer.NormalizedMessage(
        platform="slack",
        session_id="s1",
        user_id=user_id,
        text="hi",
        attachments=[],
        reply_func=reply_func,
        channel_id=channel_id,
        session_context=normalizer.SessionContext(
            platform="slack",
            sender_id=user_id,
            chat_type=chat_type,
            channel_name=channel_id,
        ),
    )


async def test_allowed_user_proceeds(monkeypatch, stub_loop, approvals):
    _set_agent(monkeypatch, _agent(ImAccess(allow_users=["u1"]), supports_dm=True))
    await normalizer.route(_msg([]))
    assert stub_loop["loop"] is True


async def test_locally_approved_user_proceeds(monkeypatch, stub_loop, approvals):
    approvals.approve("u1")
    _set_agent(monkeypatch, _agent(ImAccess(require_approval=True), supports_dm=True))
    await normalizer.route(_msg([]))
    assert stub_loop["loop"] is True


async def test_disallowed_user_with_require_approval_blocked_and_pending(
    monkeypatch, stub_loop, approvals
):
    _set_agent(monkeypatch, _agent(ImAccess(require_approval=True), supports_dm=True))
    replies = []
    await normalizer.route(_msg(replies))
    assert stub_loop["loop"] is False  # never reached the loop
    assert replies and replies[0] == normalizer._REJECTION_MSG
    assert "u1" in approvals.list_pending()  # recorded for later approval


@pytest.mark.parametrize(
    ("supports_dm", "allow_users", "allow_all_users", "user_id", "should_run"),
    [
        (True, ["u1"], False, "u1", True),
        (False, ["u1"], False, "u1", False),
        (True, [], True, "u-stranger", True),
        (True, ["u1"], False, "u-stranger", False),
    ],
)
async def test_dm_gate_branches_on_capability_and_user_access(
    monkeypatch,
    stub_loop,
    approvals,
    supports_dm,
    allow_users,
    allow_all_users,
    user_id,
    should_run,
):
    _set_agent(
        monkeypatch,
        _agent(
            ImAccess(allow_users=allow_users, allow_all_users=allow_all_users),
            supports_dm=supports_dm,
        ),
    )

    replies = []
    await normalizer.route(_msg(replies, user_id=user_id, chat_type="dm"))

    assert stub_loop["loop"] is should_run
    if should_run:
        assert normalizer._REJECTION_MSG not in replies
    else:
        assert replies and replies[0] == normalizer._REJECTION_MSG


@pytest.mark.parametrize(
    ("supports_groups", "allow_groups", "user_id", "channel_id", "should_run"),
    [
        (True, ["C1"], "u-stranger", "C1", True),
        (False, ["C1"], "u-stranger", "C1", False),
        (True, ["C1"], "u-stranger", "C2", False),
    ],
)
async def test_group_gate_branches_on_capability_and_group_allowlist(
    monkeypatch,
    stub_loop,
    approvals,
    supports_groups,
    allow_groups,
    user_id,
    channel_id,
    should_run,
):
    _set_agent(
        monkeypatch,
        _agent(
            ImAccess(allow_groups=allow_groups, allow_users=[]),
            supports_groups=supports_groups,
        ),
    )

    replies = []
    await normalizer.route(
        _msg(replies, user_id=user_id, channel_id=channel_id, chat_type="channel")
    )

    assert stub_loop["loop"] is should_run
    if should_run:
        assert normalizer._REJECTION_MSG not in replies
    else:
        assert replies and replies[0] == normalizer._REJECTION_MSG


async def test_default_closed_blocks_dm_and_empty_group_allowlist(
    monkeypatch, stub_loop, approvals
):
    _set_agent(monkeypatch, _agent(ImAccess()))

    dm_replies = []
    await normalizer.route(_msg(dm_replies, chat_type="dm"))
    assert stub_loop["loop"] is False
    assert dm_replies and dm_replies[0] == normalizer._REJECTION_MSG

    _set_agent(
        monkeypatch,
        _agent(
            ImAccess(allow_all_users=True),
            supports_groups=True,
        ),
    )
    stub_loop["loop"] = False
    group_replies = []
    await normalizer.route(_msg(group_replies, channel_id="C_anything", chat_type="channel"))
    assert stub_loop["loop"] is False
    assert group_replies and group_replies[0] == normalizer._REJECTION_MSG


async def test_zero_db_proof_routing_decides_locally(monkeypatch, stub_loop, approvals):
    # Rig the platform allowlist/user-store to raise; routing must still decide.
    import fleetent.platform.im_gateway_management as platform_im
    import fleetent.user_store as user_store

    def boom(*a, **k):
        raise AssertionError("platform DB must not be read on the runtime path")

    monkeypatch.setattr(platform_im, "is_allowed", boom)
    monkeypatch.setattr(platform_im, "check_allowed_by_user_id", boom)
    monkeypatch.setattr(user_store, "_conn", boom)

    _set_agent(monkeypatch, _agent(ImAccess(allow_users=["u1"]), supports_dm=True))
    await normalizer.route(_msg([]))
    assert stub_loop["loop"] is True
