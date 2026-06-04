"""Terminal rendering of gateway events as prompt_toolkit ``FormattedText``.

Why not rich here: under prompt_toolkit's ``patch_stdout`` (the app runs the live
prompt concurrently with streamed output), writing raw ANSI from rich to stdout
shows up literally (``?[36m`` garbage) and fragments mid-stream. prompt_toolkit's
own ``FormattedText`` + ``print_formatted_text`` is the patch_stdout-safe path.

These functions are pure (event → FormattedText), so they unit-test without a
terminal; the app emits them via ``print_formatted_text``.
"""

from typing import Any

from prompt_toolkit.formatted_text import FormattedText

from fleetent.tui import protocol as p

# Tool results can be large (file dumps, shell output); show a head + a marker.
RESULT_TRUNCATE_LIMIT = 800


def _truncate(text: str, limit: int = RESULT_TRUNCATE_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def format_event(event: dict[str, Any]) -> FormattedText | None:
    """Render one gateway event to FormattedText, or None if nothing to show.

    Newlines are baked in so the app can always emit with ``end=""`` — streamed
    ``text_delta`` stays on the same line, structured events stand on their own.
    """
    event_type = event.get("type", "")
    payload = event.get("payload", {}) or {}

    if event_type == p.EVENT_TEXT_DELTA:
        return FormattedText([("", str(payload.get("content", "")))])
    if event_type == p.EVENT_TOOL_CALL:
        name = str(payload.get("name", "?"))
        args = payload.get("args", {})
        return FormattedText([("ansicyan", f"\n🔧 {name} "), ("ansibrightblack", f"{args}\n")])
    if event_type == p.EVENT_TOOL_RESULT:
        name = str(payload.get("name", "?"))
        content = _truncate(str(payload.get("content", "")))
        return FormattedText([("ansigreen", f"\n← {name}: "), ("", f"{content}\n")])
    if event_type == p.EVENT_ERROR:
        return FormattedText([("ansired", f"\n⚠ error: {payload.get('content', '')}\n")])
    if event_type == p.EVENT_APPROVAL_REQUIRED:
        approval_id = payload.get("approval_id", "?")
        tool = payload.get("tool", "?")
        risk = payload.get("risk", "?")
        return FormattedText(
            [
                ("ansiyellow", f"\n⚠ approval required [{approval_id}] "),
                ("", f"tool={tool} risk={risk}\n"),
                ("ansibrightblack", f"   /approve {approval_id} approved|rejected\n"),
            ]
        )
    if event_type == p.EVENT_DONE:
        return FormattedText([("", "\n")])  # close the streamed line
    return None


def format_status(message: str) -> FormattedText:
    """Render a dim status line (connection state, command feedback, etc.)."""
    return FormattedText([("ansibrightblack", message)])
