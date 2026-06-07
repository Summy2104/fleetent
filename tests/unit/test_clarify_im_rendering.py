"""Tests for clarify IM rendering (Slack, Telegram, normalizer fallback)."""

from __future__ import annotations

from fleetent.im_gateway.clarify_renderer import (
    render_clarify_slack,
    render_clarify_telegram,
    render_clarify_text,
)

# ── Slack Block Kit rendering ─────────────────────────────────────────────────


def test_slack_render_choices_produces_block_kit():
    blocks = render_clarify_slack(
        question="How to proceed?",
        choices=["Option A", "Option B", "Option C"],
        session_id="s1",
    )
    assert isinstance(blocks, list)
    # Should have at least a section (question) + actions (buttons)
    block_types = [b["type"] for b in blocks]
    assert "section" in block_types
    assert "actions" in block_types


def test_slack_render_buttons_count_matches_choices():
    choices = ["Yes", "No", "Maybe"]
    blocks = render_clarify_slack("Pick?", choices, session_id="s2")
    actions_block = next(b for b in blocks if b["type"] == "actions")
    assert len(actions_block["elements"]) == len(choices)


def test_slack_render_button_text_matches_choice():
    blocks = render_clarify_slack("Choose?", ["Alpha", "Beta"], session_id="s3")
    actions = next(b for b in blocks if b["type"] == "actions")
    texts = [el["text"]["text"] for el in actions["elements"]]
    assert "Alpha" in texts
    assert "Beta" in texts


def test_slack_render_button_value_encodes_session():
    blocks = render_clarify_slack("Q?", ["X"], session_id="session_abc")
    actions = next(b for b in blocks if b["type"] == "actions")
    value = actions["elements"][0]["value"]
    assert "session_abc" in value


def test_slack_render_open_question_no_buttons():
    blocks = render_clarify_slack("What is your goal?", choices=None, session_id="s4")
    block_types = [b["type"] for b in blocks]
    assert "actions" not in block_types


# ── Telegram InlineKeyboard rendering ────────────────────────────────────────


def test_telegram_render_choices_produces_inline_keyboard():
    markup = render_clarify_telegram(
        question="Choose?",
        choices=["A", "B"],
        session_id="ts1",
    )
    assert "inline_keyboard" in markup
    # Flatten buttons
    buttons = [btn for row in markup["inline_keyboard"] for btn in row]
    assert len(buttons) == 2


def test_telegram_render_button_text_and_data():
    markup = render_clarify_telegram("Pick?", ["Yes", "No"], session_id="ts2")
    buttons = [btn for row in markup["inline_keyboard"] for btn in row]
    texts = [b["text"] for b in buttons]
    assert "Yes" in texts
    assert "No" in texts
    # callback_data should encode session + choice
    for b in buttons:
        assert "ts2" in b["callback_data"]


def test_telegram_render_open_question_returns_none():
    result = render_clarify_telegram("Open question?", choices=None, session_id="ts3")
    assert result is None


# ── Text fallback rendering ───────────────────────────────────────────────────


def test_text_render_choices_numbered_list():
    text = render_clarify_text("Pick one?", ["A", "B", "C"], session_id="fs1")
    assert "1." in text or "1)" in text
    assert "A" in text
    assert "B" in text
    assert "C" in text


def test_text_render_includes_question():
    text = render_clarify_text("What is your name?", ["Alice", "Bob"], session_id="fs2")
    assert "What is your name?" in text


def test_text_render_open_question_no_choices():
    text = render_clarify_text("Describe your goal?", choices=None, session_id="fs3")
    assert "Describe your goal?" in text
