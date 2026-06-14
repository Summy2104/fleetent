"""Unit tests for the send_im_message builtin tool (send-im-message-tool).

The tool sends via ToolContext-injected outbound connectors; outbound primitives
are mocked. Failure modes return explanatory text, never raise.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fleetent.im_gateway.normalizer import SessionContext
from fleetent.outbound import DeliveryReceipt
from fleetent.tools.registry import ToolContext, get_risk_level


def _ctx(platform: str = "slack", connector: object | None = None) -> ToolContext:
    return ToolContext(
        session_context=SessionContext(platform=platform, sender_id="U_SENDER"),
        outbound_connectors={platform: connector if connector is not None else object()},
    )


def test_send_im_message_registered_as_medium_risk() -> None:
    import fleetent.tools.builtin_tools  # noqa: F401 — registration side effect

    assert get_risk_level("send_im_message") == "medium"


async def test_dm_sent_via_session_platform_connector() -> None:
    from fleetent.tools.builtin_tools import send_im_message

    connector = object()
    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch(
            "fleetent.outbound.send_to",
            AsyncMock(
                return_value=DeliveryReceipt(
                    ok=True, platform="slack", target="x", target_type="user", kind="text"
                )
            ),
        ) as send_to,
    ):
        result = await send_im_message(
            target="U_OTHER", text="hello", tool_context=_ctx(connector=connector)
        )

    args = send_to.call_args
    assert args.args[0] == "slack"
    assert args.args[1] is connector
    assert args.args[2] == "U_OTHER"
    assert args.args[3] == "hello"
    assert args.kwargs.get("target_type", "user") == "user"
    assert "U_OTHER" in result


async def test_channel_post_passes_target_type() -> None:
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch(
            "fleetent.outbound.send_to",
            AsyncMock(
                return_value=DeliveryReceipt(
                    ok=True, platform="slack", target="x", target_type="user", kind="text"
                )
            ),
        ) as send_to,
    ):
        await send_im_message(
            target="C_NOTICE",
            text="notice",
            target_type="channel",
            tool_context=_ctx(),
        )

    assert send_to.call_args.kwargs["target_type"] == "channel"


async def test_explicit_platform_overrides_session_platform() -> None:
    from fleetent.tools.builtin_tools import send_im_message

    tg_connector = object()
    ctx = ToolContext(
        session_context=SessionContext(platform="slack", sender_id="U_S"),
        outbound_connectors={"slack": object(), "telegram": tg_connector},
    )
    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch(
            "fleetent.outbound.send_to",
            AsyncMock(
                return_value=DeliveryReceipt(
                    ok=True, platform="slack", target="x", target_type="user", kind="text"
                )
            ),
        ) as send_to,
    ):
        await send_im_message(target="12345", text="hi", platform="telegram", tool_context=ctx)

    assert send_to.call_args.args[0] == "telegram"
    assert send_to.call_args.args[1] is tg_connector


async def test_missing_connector_returns_explanation_without_raising() -> None:
    from fleetent.tools.builtin_tools import send_im_message

    ctx = ToolContext(
        session_context=SessionContext(platform="slack", sender_id="U_S"),
        outbound_connectors={},
    )
    result = await send_im_message(target="U_X", text="hi", tool_context=ctx)

    assert isinstance(result, str)
    assert "不支持" in result or "无可用" in result


async def test_no_platform_at_all_returns_explanation() -> None:
    from fleetent.tools.builtin_tools import send_im_message

    result = await send_im_message(target="U_X", text="hi", tool_context=ToolContext())

    assert isinstance(result, str)
    assert "platform" in result or "平台" in result


async def test_unreachable_target_returns_explanation_and_skips_send() -> None:
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=False)),
        patch(
            "fleetent.outbound.send_to",
            AsyncMock(
                return_value=DeliveryReceipt(
                    ok=True, platform="slack", target="x", target_type="user", kind="text"
                )
            ),
        ) as send_to,
    ):
        result = await send_im_message(target="U_GHOST", text="hi", tool_context=_ctx())

    send_to.assert_not_called()
    assert "无法触达" in result or "不可达" in result


async def test_send_failure_returns_failure_text() -> None:
    from fleetent.tools.builtin_tools import send_im_message

    with (
        patch("fleetent.outbound.is_reachable", AsyncMock(return_value=True)),
        patch(
            "fleetent.outbound.send_to",
            AsyncMock(
                return_value=DeliveryReceipt(
                    ok=False,
                    platform="slack",
                    target="x",
                    target_type="user",
                    kind="text",
                    error="boom",
                )
            ),
        ),
    ):
        result = await send_im_message(target="U_OTHER", text="hi", tool_context=_ctx())

    assert "失败" in result
