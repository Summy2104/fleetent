"""Tests for Slack realtime status indicator: tool-name → readable status mapping
and the Assistants API status flow (_make_status_funcs)."""

from __future__ import annotations

from unittest.mock import MagicMock

# ── _tool_status_text ─────────────────────────────────────────────────────────


def test_tool_status_text_mapped():
    from fleetent.im_gateway.slack import _tool_status_text

    s = _tool_status_text("google-workspace__manage_drive")
    assert "Google Drive" in s
    assert s.endswith("...")


def test_tool_status_text_prefix_match():
    from fleetent.im_gateway.slack import _tool_status_text

    # Unknown sub-tool under a known google-workspace prefix still gets a label
    s = _tool_status_text("google-workspace__manage_drive__weird_subop")
    assert s.endswith("...")
    assert "🔧" in s or "Google Drive" in s


def test_tool_status_text_fallback_strips_namespace():
    from fleetent.im_gateway.slack import _tool_status_text

    s = _tool_status_text("customserver__do_something")
    # Namespace stripped, underscores → spaces
    assert "do something" in s
    assert "customserver" not in s


# ── _make_status_funcs ────────────────────────────────────────────────────────


async def test_status_funcs_sets_initial_status():
    from fleetent.im_gateway import slack as slack_mod

    calls: list[dict] = []
    client = MagicMock()

    async def fake_set(**kwargs):
        calls.append(kwargs)

    client.assistant_threads_setStatus = fake_set

    await slack_mod._make_status_funcs(client, "C1", "123.456", say=None)

    assert len(calls) == 1
    assert calls[0]["channel_id"] == "C1"
    assert calls[0]["thread_ts"] == "123.456"
    assert "思考中" in calls[0]["status"]


async def test_status_funcs_progress_updates_with_readable_text():
    from fleetent.im_gateway import slack as slack_mod

    calls: list[str] = []
    client = MagicMock()

    async def fake_set(**kwargs):
        calls.append(kwargs["status"])

    client.assistant_threads_setStatus = fake_set

    _reply, progress = await slack_mod._make_status_funcs(client, "C1", "123.456", say=None)
    await progress({"type": "tool_call", "name": "google-workspace__manage_drive"})

    # initial + progress
    assert any("Google Drive" in s for s in calls)


async def test_status_funcs_reply_clears_status_and_calls_say():
    from fleetent.im_gateway import slack as slack_mod

    statuses: list[str] = []
    said: list[str] = []
    client = MagicMock()

    async def fake_set(**kwargs):
        statuses.append(kwargs["status"])

    client.assistant_threads_setStatus = fake_set

    async def fake_say(text, thread_ts=None):
        said.append(text)

    reply, _progress = await slack_mod._make_status_funcs(client, "C1", "123.456", say=fake_say)
    await reply("final answer")

    # status cleared (empty string) and reply sent
    assert "" in statuses
    assert said == ["final answer"]


async def test_status_funcs_degrades_when_setstatus_unavailable():
    from fleetent.im_gateway import slack as slack_mod

    said: list[str] = []
    client = MagicMock()

    async def fake_set(**kwargs):
        raise RuntimeError("assistant feature not enabled")

    client.assistant_threads_setStatus = fake_set

    async def fake_say(text, thread_ts=None):
        said.append(text)

    reply, progress = await slack_mod._make_status_funcs(client, "C1", "123.456", say=fake_say)
    # progress must be a no-op (status unavailable), reply must still say()
    await progress({"type": "tool_call", "name": "run_code"})
    await reply("answer despite no status")

    assert said == ["answer despite no status"]


async def test_status_funcs_initial_passes_loading_messages():
    from fleetent.im_gateway import slack as slack_mod

    calls: list[dict] = []
    client = MagicMock()

    async def fake_set(**kwargs):
        calls.append(kwargs)

    client.assistant_threads_setStatus = fake_set

    await slack_mod._make_status_funcs(client, "C1", "123.456", say=None)

    assert calls[0].get("loading_messages")
    assert "思考中" in " ".join(calls[0]["loading_messages"])


async def test_status_funcs_progress_passes_loading_messages():
    from fleetent.im_gateway import slack as slack_mod

    calls: list[dict] = []
    client = MagicMock()

    async def fake_set(**kwargs):
        calls.append(kwargs)

    client.assistant_threads_setStatus = fake_set

    _reply, progress = await slack_mod._make_status_funcs(client, "C1", "123.456", say=None)
    await progress(
        {
            "type": "tool_call",
            "names": ["google-workspace__manage_calendar", "google-workspace__manage_drive"],
        }
    )

    progress_call = calls[-1]
    lm = progress_call.get("loading_messages")
    assert lm is not None
    joined = " ".join(lm)
    assert "日历" in joined and "Google Drive" in joined
