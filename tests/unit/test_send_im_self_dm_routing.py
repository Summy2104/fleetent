"""Unit: send_im_message conversation-pinning guardrail (fix-send-im-channel-self-dm-routing).

Covers the pure decision helper `_resolve_self_dm_redirect`: in a CHANNEL conversation, a
self-DM (target == sender, target_type == "user") must be redirected to the channel thread
(send_file parity) instead of the sender's private DM. Third-party sends, channel posts, and
DM conversations are left untouched. Pure inputs only — no DB/HTTP/store (unit boundary)."""

from types import SimpleNamespace

from fleetent.tools.builtin_tools import _resolve_self_dm_redirect


def _addr(chat_type="channel", chat_id="C_CHAN", thread_id="111.222"):
    # Duck-typed stand-in for outbound.ConversationAddress (only the read fields matter).
    return SimpleNamespace(chat_type=chat_type, chat_id=chat_id, thread_id=thread_id)


def test_channel_self_dm_redirects_to_channel_thread():
    out = _resolve_self_dm_redirect("U_SELF", "user", _addr(), "U_SELF")
    assert out == {"recipient": "C_CHAN", "target_type": "channel", "thread": "111.222"}


def test_third_party_user_not_redirected():
    assert _resolve_self_dm_redirect("U_OTHER", "user", _addr(), "U_SELF") is None


def test_channel_target_type_not_redirected():
    # Posting to a channel target is already a channel post — no self-DM rewrite.
    assert _resolve_self_dm_redirect("C_NOTICE", "channel", _addr(), "U_SELF") is None


def test_dm_conversation_not_redirected():
    # The DM itself is the conversation; nothing to pin.
    assert _resolve_self_dm_redirect("U_SELF", "user", _addr(chat_type="dm"), "U_SELF") is None


def test_missing_address_not_redirected():
    assert _resolve_self_dm_redirect("U_SELF", "user", None, "U_SELF") is None


def test_whitespace_tolerant_match():
    out = _resolve_self_dm_redirect("  U_SELF ", "user", _addr(), "U_SELF")
    assert out == {"recipient": "C_CHAN", "target_type": "channel", "thread": "111.222"}


def test_empty_sender_or_target_not_redirected():
    assert _resolve_self_dm_redirect("", "user", _addr(), "") is None
    assert _resolve_self_dm_redirect("U_SELF", "user", _addr(), "") is None
    assert _resolve_self_dm_redirect("", "user", _addr(), "U_SELF") is None


def test_none_thread_preserved():
    out = _resolve_self_dm_redirect("U_SELF", "user", _addr(thread_id=None), "U_SELF")
    assert out == {"recipient": "C_CHAN", "target_type": "channel", "thread": None}


# --- wiring into send_im_message (task 3): the override reaches both outbound calls ----------

from unittest.mock import AsyncMock, patch  # noqa: E402

from fleetent.im_gateway.normalizer import SessionContext  # noqa: E402
from fleetent.outbound import ConversationAddress, DeliveryReceipt  # noqa: E402
from fleetent.tools.registry import ToolContext  # noqa: E402


def _channel_ctx(sender="U_SELF"):
    # A channel conversation rooted at C_CHAN / thread 111.222, sender U_SELF.
    return ToolContext(
        session_context=SessionContext(platform="slack", sender_id=sender),
        outbound_connectors={"slack": object()},
        conversation_address=ConversationAddress(
            platform="slack",
            chat_id="C_CHAN",
            target_type="channel",
            thread_id="111.222",
            user_id=sender,
            chat_type="channel",
        ),
    )


def _ok(kind, target):
    return DeliveryReceipt(ok=True, platform="slack", target=target, target_type="x", kind=kind)


async def test_wiring_channel_self_dm_text_pinned_to_channel_thread():
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=_ok("text", "C_CHAN"))) as st,
    ):
        await send_im_message(target="U_SELF", text="here", tool_context=_channel_ctx())

    # Text must go to the channel thread, not the sender's DM.
    assert st.call_args.args[2] == "C_CHAN"
    assert st.call_args.kwargs["target_type"] == "channel"
    assert st.call_args.kwargs["thread"] == "111.222"


async def test_wiring_channel_self_dm_file_pinned_to_channel_thread():
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=_ok("text", "C_CHAN"))),
        patch(
            "fleetent.tools.builtin_tools._resolve_outbound_path",
            return_value="/host/report.png",
        ),
        patch(
            "fleetent.outbound.send_file_to", AsyncMock(return_value=_ok("file", "C_CHAN"))
        ) as sf,
    ):
        await send_im_message(
            target="U_SELF", text="here", files=["report.png"], tool_context=_channel_ctx()
        )

    assert sf.call_args.args[2] == "C_CHAN"
    assert sf.call_args.kwargs["target_type"] == "channel"
    assert sf.call_args.kwargs["thread"] == "111.222"


async def test_wiring_third_party_not_pinned():
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch("fleetent.outbound.send_to", AsyncMock(return_value=_ok("text", "U_OTHER"))) as st,
    ):
        await send_im_message(target="U_OTHER", text="hi", tool_context=_channel_ctx())

    # Third-party send is untouched: still the original user target.
    assert st.call_args.args[2] == "U_OTHER"
    assert st.call_args.kwargs["target_type"] == "user"
