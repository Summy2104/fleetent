"""Platform-specific rendering for the clarify tool.

Each renderer takes a question, optional choices, and session_id, and returns
a platform-native message payload. The session_id is embedded in button
callback data so the IM gateway can route the user's click to user_input_gate.

Renderers are pure functions with no I/O — they only build the payload dict/list.
The actual send is done by each IM adapter.
"""

from __future__ import annotations

import json


def render_clarify_slack(
    question: str,
    choices: list[str] | None,
    session_id: str,
) -> list[dict[str, object]]:
    """Build a Slack Block Kit message for a clarify prompt.

    Returns a blocks list:
    - A section block with the question text.
    - An actions block with one Button per choice (omitted for open questions).
    """
    blocks: list[dict[str, object]] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": question},
        }
    ]

    if choices:
        elements = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": choice},
                # value encodes session_id + choice so the callback handler knows
                # which gate to answer and what the user selected.
                "value": json.dumps({"session_id": session_id, "choice": choice}),
                "action_id": f"clarify_{session_id}_{i}",
            }
            for i, choice in enumerate(choices)
        ]
        blocks.append({"type": "actions", "elements": elements})

    return blocks


def render_clarify_telegram(
    question: str,
    choices: list[str] | None,
    session_id: str,
) -> dict[str, object] | None:
    """Build a Telegram InlineKeyboardMarkup dict for a clarify prompt.

    Returns a dict with `inline_keyboard` key (list of button rows), or None
    for open-ended questions (no buttons to render).
    """
    if not choices:
        return None

    # One button per row for clarity; could be 2-per-row for short labels.
    rows = [
        [
            {
                "text": choice,
                # callback_data encodes session_id + choice as compact JSON
                "callback_data": json.dumps({"sid": session_id, "v": choice}),
            }
        ]
        for choice in choices
    ]
    return {"inline_keyboard": rows}


def render_clarify_text(
    question: str,
    choices: list[str] | None,
    session_id: str,
) -> str:
    """Render a clarify prompt as plain numbered text (fallback for non-IM sessions).

    Used when there is no IM rendering layer (API, webhook, TUI).
    """
    lines = [question]
    if choices:
        for i, choice in enumerate(choices, 1):
            lines.append(f"{i}. {choice}")
    return "\n".join(lines)
