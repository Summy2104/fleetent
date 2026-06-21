"""Tests for the Slack Assistant-container path: status bound to the real assistant
thread via slack-bolt's Assistant middleware, and batched per-tool status aggregation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

# ── status text aggregation ───────────────────────────────────────────────────


def test_status_text_for_event_aggregates_all_tools():
    from fleetent.im_gateway.slack import _status_text_for_event

    s = _status_text_for_event(
        {
            "type": "tool_call",
            "names": ["google-workspace__manage_calendar", "google-workspace__manage_drive"],
        }
    )
    # Both tools represented, not only the last one.
    assert "日历" in s
    assert "Google Drive" in s
    assert s.endswith("...")


def test_status_text_for_event_back_compat_name_only():
    from fleetent.im_gateway.slack import _status_text_for_event

    s = _status_text_for_event({"type": "tool_call", "name": "google-workspace__manage_drive"})
    assert "Google Drive" in s


def test_status_text_for_event_truncates_many_tools():
    from fleetent.im_gateway.slack import _status_text_for_event

    names = [f"customserver__op_{i}" for i in range(6)]
    s = _status_text_for_event({"type": "tool_call", "names": names})
    assert "6" in s  # surfaces the total count when truncating


# ── create_app registers the Assistant container ──────────────────────────────


def test_create_app_registers_assistant_and_keeps_fallback():
    from fleetent.im_gateway import slack as slack_mod

    fake_app = MagicMock()
    fake_app.event.return_value = lambda fn: fn  # @app.event(...) decorator passthrough

    with patch("slack_bolt.async_app.AsyncApp", return_value=fake_app):
        slack_mod.create_app("agent1", {"bot_token": "xoxb-test"})

    # Assistant container registered for the assistant-pane / DM path.
    assert fake_app.assistant.called
    # Channel @mention path retained.
    event_names = [c.args[0] for c in fake_app.event.call_args_list if c.args]
    assert "app_mention" in event_names


# ── assistant user_message routing binds status to the assistant thread ────────


def _capture_routed(monkeypatch):
    routed: dict = {}

    async def fake_route(msg):
        routed["msg"] = msg

    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)
    monkeypatch.setattr(
        "fleetent.im_gateway.access.resolve_identity",
        lambda p, uid, owner_id="default": uid,
        raising=False,
    )
    monkeypatch.setattr(
        "fleetent.im_gateway.slack._download_attachments",
        AsyncMock(return_value=[]),
    )
    return routed


def _ctx(channel_id="C-ASSIST", thread_ts="111.222"):
    ctx = MagicMock()
    ctx.channel_id = channel_id
    ctx.thread_ts = thread_ts
    return ctx


async def test_assistant_message_routes_with_bound_status(monkeypatch):
    """progress/reply use the middleware-bound set_status/say, never event.ts."""
    from fleetent.im_gateway import slack as slack_mod

    routed = _capture_routed(monkeypatch)
    set_status = AsyncMock()
    say = AsyncMock()
    client = MagicMock()
    payload = {"user": "U1", "text": "hi", "ts": "999.000"}  # ts must NOT be used as thread

    await slack_mod._route_assistant_message(
        payload=payload,
        context=_ctx(),
        set_status=set_status,
        say=say,
        client=client,
        agent_name="agent1",
        bot_token="xoxb-test",
    )

    msg = routed["msg"]
    assert msg.platform == "slack"
    assert msg.channel_id == "C-ASSIST"
    assert msg.text == "hi"
    assert msg.progress_func is not None and msg.reply_func is not None


async def test_assistant_progress_aggregates_batch(monkeypatch):
    from fleetent.im_gateway import slack as slack_mod

    routed = _capture_routed(monkeypatch)
    set_status = AsyncMock()
    say = AsyncMock()

    await slack_mod._route_assistant_message(
        payload={"user": "U1", "text": "hi"},
        context=_ctx(),
        set_status=set_status,
        say=say,
        client=MagicMock(),
        agent_name="a",
        bot_token="b",
    )
    await routed["msg"].progress_func(
        {
            "type": "tool_call",
            "names": ["google-workspace__manage_calendar", "google-workspace__manage_drive"],
        }
    )

    statuses = [c.args[0] if c.args else c.kwargs.get("status") for c in set_status.call_args_list]
    assert any("日历" in (s or "") and "Google Drive" in (s or "") for s in statuses)


async def test_assistant_reply_clears_status_and_says(monkeypatch):
    from fleetent.im_gateway import slack as slack_mod

    routed = _capture_routed(monkeypatch)
    set_status = AsyncMock()
    say = AsyncMock()

    await slack_mod._route_assistant_message(
        payload={"user": "U1", "text": "hi"},
        context=_ctx(),
        set_status=set_status,
        say=say,
        client=MagicMock(),
        agent_name="a",
        bot_token="b",
    )
    await routed["msg"].reply_func("final answer")

    # Status cleared with empty string, and reply delivered via say().
    cleared = [c for c in set_status.call_args_list if (c.args and c.args[0] == "")]
    assert cleared
    say.assert_awaited_with("final answer")


async def test_assistant_degrade_setstatus_fails_still_says(monkeypatch):
    from fleetent.im_gateway import slack as slack_mod

    routed = _capture_routed(monkeypatch)
    set_status = AsyncMock(side_effect=RuntimeError("assistant feature not enabled"))
    say = AsyncMock()

    await slack_mod._route_assistant_message(
        payload={"user": "U1", "text": "hi"},
        context=_ctx(),
        set_status=set_status,
        say=say,
        client=MagicMock(),
        agent_name="a",
        bot_token="b",
    )
    # progress must swallow the failure; reply must still deliver.
    await routed["msg"].progress_func({"type": "tool_call", "names": ["run_code"]})
    await routed["msg"].reply_func("answer despite no status")

    say.assert_awaited_with("answer despite no status")


async def test_assistant_progress_passes_loading_messages(monkeypatch):
    """set_status receives loading_messages mirroring every tool in the batch."""
    from fleetent.im_gateway import slack as slack_mod

    routed = _capture_routed(monkeypatch)
    set_status = AsyncMock()
    say = AsyncMock()

    await slack_mod._route_assistant_message(
        payload={"user": "U1", "text": "hi"},
        context=_ctx(),
        set_status=set_status,
        say=say,
        client=MagicMock(),
        agent_name="a",
        bot_token="b",
    )
    set_status.reset_mock()  # drop the initial "thinking" call
    await routed["msg"].progress_func(
        {
            "type": "tool_call",
            "names": ["google-workspace__manage_calendar", "google-workspace__manage_drive"],
        }
    )

    lm = set_status.call_args.kwargs.get("loading_messages")
    assert lm is not None
    joined = " ".join(lm)
    assert "日历" in joined and "Google Drive" in joined
    assert len(lm) >= 2  # one entry per in-flight tool


async def test_assistant_initial_status_passes_loading_messages(monkeypatch):
    """The initial thinking status also sets loading_messages (no Slack default leak)."""
    from fleetent.im_gateway import slack as slack_mod

    _capture_routed(monkeypatch)
    set_status = AsyncMock()

    await slack_mod._route_assistant_message(
        payload={"user": "U1", "text": "hi"},
        context=_ctx(),
        set_status=set_status,
        say=AsyncMock(),
        client=MagicMock(),
        agent_name="a",
        bot_token="b",
    )

    # First set_status call is the initial "thinking" state.
    first = set_status.call_args_list[0]
    assert first.kwargs.get("loading_messages")
    assert "思考中" in " ".join(first.kwargs["loading_messages"])


async def test_assistant_message_carries_outbound_connectors(monkeypatch):
    """Assistant-pane path injects the Slack client, same as the channel path."""
    from fleetent.im_gateway import slack as slack_mod

    routed = _capture_routed(monkeypatch)
    client = MagicMock()

    await slack_mod._route_assistant_message(
        payload={"user": "U1", "text": "hi", "ts": "999.000"},
        context=_ctx(),
        set_status=AsyncMock(),
        say=AsyncMock(),
        client=client,
        agent_name="agent1",
        bot_token="xoxb-test",
    )

    assert routed["msg"].outbound_connectors == {"slack": client}


# ── empty-reply guard (no_text) ────────────────────────────────────────────────


def test_has_postable_content():
    from fleetent.im_gateway.slack import _has_postable_content

    assert _has_postable_content("", None) is False
    assert _has_postable_content("   ", None) is False
    assert _has_postable_content("\n", None) is False
    assert _has_postable_content("hi", None) is True
    assert _has_postable_content("", [{"type": "section"}]) is True


async def test_make_status_funcs_skips_empty_reply():
    from fleetent.im_gateway import slack as slack_mod

    client = MagicMock()
    client.assistant_threads_setStatus = AsyncMock()
    say = AsyncMock()
    reply_func, _ = await slack_mod._make_status_funcs(client, "C1", "t1", say)
    await reply_func("")
    await reply_func("   ")
    say.assert_not_awaited()  # empty text + no blocks must NOT call Slack (no_text)


async def test_make_status_funcs_posts_nonempty_or_blocks():
    from fleetent.im_gateway import slack as slack_mod

    client = MagicMock()
    client.assistant_threads_setStatus = AsyncMock()
    say = AsyncMock()
    reply_func, _ = await slack_mod._make_status_funcs(client, "C1", "t1", say)
    await reply_func("hi")
    say.assert_awaited()  # non-empty text posts
    say.reset_mock()
    await reply_func("", blocks=[{"type": "section"}])
    say.assert_awaited()  # blocks-only message still posts
