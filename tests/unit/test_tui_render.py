"""TUI rendering of gateway events to FormattedText (tui-gateway 7.1)."""

from prompt_toolkit.formatted_text import FormattedText

from fleetent.tui import protocol as p
from fleetent.tui import render


def _plain(ft: FormattedText | None) -> str:
    """Concatenate the text of a FormattedText (drop styles) for assertions."""
    assert ft is not None
    return "".join(text for _style, text in ft)


def test_text_delta_renders_content_plain():
    out = _plain(
        render.format_event(p.make_event(p.EVENT_TEXT_DELTA, {"content": "hello world"})["params"])
    )
    assert out == "hello world"  # no newline, no styling wrapper text


def test_tool_call_shows_name_and_args():
    out = _plain(
        render.format_event(
            {"type": "tool_call", "payload": {"name": "calculate", "args": {"x": 1}}}
        )
    )
    assert "calculate" in out and "x" in out


def test_tool_result_truncates_long_content():
    long = "A" * (render.RESULT_TRUNCATE_LIMIT + 200)
    out = _plain(
        render.format_event({"type": "tool_result", "payload": {"name": "shell", "content": long}})
    )
    assert "shell" in out
    assert "…" in out
    assert long not in out  # full content not shown


def test_error_event_is_rendered():
    out = _plain(render.format_event({"type": "error", "payload": {"content": "boom failure"}}))
    assert "boom failure" in out


def test_approval_required_shows_prompt():
    out = _plain(
        render.format_event(
            {
                "type": "approval_required",
                "payload": {"approval_id": "a1", "tool": "shell", "risk": "high"},
            }
        )
    )
    assert "a1" in out and "shell" in out and "/approve a1" in out


def test_format_status_carries_message():
    assert "connecting" in _plain(render.format_status("connecting…"))


def test_done_event_renders_newline_only():
    assert _plain(render.format_event({"type": "done", "payload": {"content": "ok"}})) == "\n"


def test_unknown_event_returns_none():
    assert render.format_event({"type": "mystery", "payload": {}}) is None
