"""Unit tests for the Slack approval button action handler (slack-approval-buttons).

The handler maps block_actions clicks to gate decisions using the clicking user's
Slack id, updates the prompt message on success, and shows an ephemeral notice on
an unauthorized/expired click. Gate and Slack client are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _no_persisted_approval(monkeypatch):
    """Default: no persisted approval row / pending entry, so the handler skips the
    restart-authz recovery + resume path. Resume tests override these."""
    from fleetent.governance import approval_store
    from fleetent.session import manager as session_mgr

    monkeypatch.setattr(approval_store, "get_approval", lambda aid: None)
    monkeypatch.setattr(session_mgr, "get_pending_approval", AsyncMock(return_value=None))


def _body(action_id: str, approval_id: str = "appr-1", user: str = "U_CLICKER") -> dict:
    return {
        "user": {"id": user},
        "channel": {"id": "C_PROMPT"},
        "message": {"ts": "1234.5678"},
        "actions": [{"action_id": action_id, "value": approval_id}],
    }


async def test_approve_click_resolves_with_clicker_id_and_updates_message() -> None:
    from fleetent.im_gateway import slack

    ack = AsyncMock()
    client = AsyncMock()
    with patch(
        "fleetent.governance.approval_router.resolve_approval_request",
        AsyncMock(return_value=True),
    ) as resolve:
        await slack.handle_approval_action(ack, _body("approval_approve"), client)

    ack.assert_called_once()
    kwargs = resolve.call_args.kwargs
    assert kwargs["approval_id"] == "appr-1"
    assert kwargs["decision"] == "approved"
    assert kwargs["approver_user_id"] == "U_CLICKER"
    assert kwargs["always"] is False
    update_kwargs = client.chat_update.call_args.kwargs
    assert update_kwargs["channel"] == "C_PROMPT"
    assert update_kwargs["ts"] == "1234.5678"
    assert update_kwargs["blocks"] == []


async def test_reject_click_resolves_rejected() -> None:
    from fleetent.im_gateway import slack

    client = AsyncMock()
    with patch(
        "fleetent.governance.approval_router.resolve_approval_request",
        AsyncMock(return_value=True),
    ) as resolve:
        await slack.handle_approval_action(
            ack=AsyncMock(), body=_body("approval_reject"), client=client
        )

    assert resolve.call_args.kwargs["decision"] == "rejected"


async def test_approve_always_click_sets_always_flag() -> None:
    from fleetent.im_gateway import slack

    client = AsyncMock()
    with patch(
        "fleetent.governance.approval_router.resolve_approval_request",
        AsyncMock(return_value=True),
    ) as resolve:
        await slack.handle_approval_action(
            ack=AsyncMock(), body=_body("approval_approve_always"), client=client
        )

    kwargs = resolve.call_args.kwargs
    assert kwargs["decision"] == "approved"
    assert kwargs["always"] is True


async def test_unauthorized_click_shows_ephemeral_and_keeps_prompt() -> None:
    from fleetent.im_gateway import slack

    client = AsyncMock()
    with patch(
        "fleetent.governance.approval_router.resolve_approval_request",
        AsyncMock(return_value=False),
    ):
        await slack.handle_approval_action(
            ack=AsyncMock(), body=_body("approval_approve", user="U_BYSTANDER"), client=client
        )

    client.chat_update.assert_not_called()
    eph_kwargs = client.chat_postEphemeral.call_args.kwargs
    assert eph_kwargs["user"] == "U_BYSTANDER"
    assert eph_kwargs["channel"] == "C_PROMPT"


async def test_reply_func_forwards_blocks_to_say() -> None:
    """The Slack reply_func accepts a blocks kwarg and forwards it to say()."""
    from fleetent.im_gateway.slack import _make_status_funcs

    client = AsyncMock()
    say = AsyncMock()
    reply_func, _ = await _make_status_funcs(client, "C1", "111.222", say)

    blocks = [{"type": "actions", "elements": []}]
    await reply_func("prompt text", blocks=blocks)

    kwargs = say.call_args.kwargs
    assert kwargs["text"] == "prompt text"
    assert kwargs["blocks"] == blocks


# ── button resolution resumes the suspended run (approval-suspend-resume Task 7) ──


async def test_approve_button_triggers_resume(monkeypatch):
    from fleetent.governance import approval_store
    from fleetent.im_gateway import normalizer, slack
    from fleetent.session import manager as session_mgr

    client = AsyncMock()
    monkeypatch.setattr(
        "fleetent.governance.approval_router.resolve_approval_request",
        AsyncMock(return_value=True),
    )
    # Approval row carries the run's (namespaced) session id; pending entry has approvers.
    monkeypatch.setattr(
        approval_store,
        "get_approval",
        lambda aid: {"session_id": "slack:dm:U_REQ:1.1", "status": "pending"},
    )
    monkeypatch.setattr(
        session_mgr,
        "get_pending_approval",
        AsyncMock(return_value={"approver_ids": ["U_CLICKER"], "tool_name": "send_im_message"}),
    )
    resume = AsyncMock(return_value="已完成。")
    monkeypatch.setattr(normalizer, "_resume_pending_in_session", resume)

    await slack.handle_approval_action(
        ack=AsyncMock(),
        body=_body("approval_approve"),
        client=client,
        agent_name="my-bot",
    )

    # Resume invoked for the approval's session + the button's decision.
    assert resume.await_args is not None
    assert resume.await_args.args[1] == "slack:dm:U_REQ:1.1"  # session_id
    assert resume.await_args.args[2] == "appr-1"  # approval_id
    assert resume.await_args.args[3] == "approved"  # decision
    # agent-hosted-im (Group 7): with no dispatcher injected (agent self-hosts its connection),
    # the button resolves + resumes in-process carrying the LIVE Slack connector so the approved
    # action actually delivers.
    resume_msg = resume.await_args.args[0]
    assert resume_msg.outbound_connectors == {"slack": client}


# ── managed mode: forward a synthesized command instead of resolving in node (AAA-8204 ②) ──


async def test_managed_button_forwards_synthesized_command(monkeypatch):
    """AAA-8204 ②: the slack edge runs in the node process under managed placement, and node
    never wired approval_store/state_db — resolving in place raises 'state_db not initialized'.
    Instead the button must synthesize the equivalent approve/reject command and forward it
    through the injected inbound dispatcher to the agent process, reusing the text-command
    resume path (③ matching + ⑥ connector resolution)."""
    from fleetent.im_gateway import inbound_dispatch, slack

    forwarded = []

    async def _disp(msg):
        forwarded.append(msg)

    monkeypatch.setattr(inbound_dispatch, "_dispatcher", _disp)  # node injected a forwarder
    resolve_spy = AsyncMock(return_value=True)
    monkeypatch.setattr("fleetent.governance.approval_router.resolve_approval_request", resolve_spy)

    ack = AsyncMock()
    client = AsyncMock()
    await slack.handle_approval_action(
        ack, _body("approval_approve_always", approval_id="ebd2986f"), client, agent_name="my-bot"
    )

    ack.assert_called_once()
    # In-place resolve is skipped — the decision is forwarded to the agent.
    resolve_spy.assert_not_awaited()
    assert len(forwarded) == 1
    fwd = forwarded[0]
    assert fwd.text == "approve always ebd2986f"
    assert fwd.user_id == "U_CLICKER"
    assert fwd.agent_name == "my-bot"
    # Prompt moved to a result state (buttons removed) to prevent double-clicks.
    assert client.chat_update.call_args.kwargs["blocks"] == []


async def test_managed_button_forwards_reject_command(monkeypatch):
    from fleetent.im_gateway import inbound_dispatch, slack

    forwarded = []

    async def _disp(msg):
        forwarded.append(msg)

    monkeypatch.setattr(inbound_dispatch, "_dispatcher", _disp)
    await slack.handle_approval_action(
        ack=AsyncMock(),
        body=_body("approval_reject", approval_id="ebd2986f"),
        client=AsyncMock(),
        agent_name="my-bot",
    )

    assert len(forwarded) == 1
    assert forwarded[0].text == "reject ebd2986f"


async def test_managed_button_resolves_clicker_slack_id_to_uuid(monkeypatch):
    """AAA-8204 ②补丁:审批 requester 存内部 uuid,按钮 clicker 是原始 Slack id。转发前须像
    入站一样经 resolve_identity 把 Slack id 解析成 uuid,否则 agent 授权失败(unauthorized)。"""
    from fleetent.im_gateway import access, inbound_dispatch, slack

    monkeypatch.setattr(
        access,
        "_im_identity_resolver",
        lambda owner, platform, puid: "26989e37-uuid" if puid == "U0B6SU8LH0D" else puid,
    )
    forwarded = []

    async def _disp(msg):
        forwarded.append(msg)

    monkeypatch.setattr(inbound_dispatch, "_dispatcher", _disp)
    await slack.handle_approval_action(
        ack=AsyncMock(),
        body=_body("approval_approve", approval_id="ebd2986f", user="U0B6SU8LH0D"),
        client=AsyncMock(),
        agent_name="my-bot",
    )

    assert len(forwarded) == 1
    assert forwarded[0].user_id == "26989e37-uuid"  # resolved, not the raw Slack id
    assert forwarded[0].text == "approve ebd2986f"


async def test_managed_button_ui_does_not_claim_approved_before_resolve(monkeypatch):
    """②补丁(b):方案A 下授权在 agent 侧异步判定,node 不得乐观 chat_update '已批准'
    (会与随后的 unauthorized 矛盾)。"""
    from fleetent.im_gateway import inbound_dispatch, slack

    async def _disp(msg):
        return None

    monkeypatch.setattr(inbound_dispatch, "_dispatcher", _disp)
    client = AsyncMock()
    await slack.handle_approval_action(
        ack=AsyncMock(),
        body=_body("approval_approve", approval_id="ebd2986f"),
        client=client,
        agent_name="my-bot",
    )

    # Prompt is moved off the buttons (no double-click) but must NOT falsely claim approval.
    update_text = client.chat_update.call_args.kwargs["text"]
    assert "已批准" not in update_text
    assert client.chat_update.call_args.kwargs["blocks"] == []


async def test_managed_button_unresolved_identity_not_forwarded(monkeypatch):
    """②补丁(a):clicker 身份解析失败(IMIdentityResolutionError)→ 不转发、不谎报,提示重试。"""
    from fleetent.im_gateway import access, inbound_dispatch, slack

    def _boom(owner, platform, puid):
        raise access.IMIdentityResolutionError("unresolved")

    monkeypatch.setattr(access, "_im_identity_resolver", _boom)
    forwarded = []

    async def _disp(msg):
        forwarded.append(msg)

    monkeypatch.setattr(inbound_dispatch, "_dispatcher", _disp)
    client = AsyncMock()
    await slack.handle_approval_action(
        ack=AsyncMock(),
        body=_body("approval_approve", approval_id="ebd2986f"),
        client=client,
        agent_name="my-bot",
    )

    assert forwarded == []  # not forwarded
    client.chat_postEphemeral.assert_called_once()
