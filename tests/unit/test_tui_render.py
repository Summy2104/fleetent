"""TUI rich rendering of gateway events (tui-gateway 7.1). Output captured via StringIO."""

from io import StringIO

from rich.console import Console

from fleetent.tui import protocol as p
from fleetent.tui import render


def _console() -> tuple[Console, StringIO]:
    buf = StringIO()
    return Console(file=buf, force_terminal=False, width=100, no_color=True), buf


def test_text_delta_writes_content():
    c, buf = _console()
    render.render_event(c, p.make_event(p.EVENT_TEXT_DELTA, {"content": "hello world"})["params"])
    assert "hello world" in buf.getvalue()


def test_tool_call_shows_name_and_args():
    c, buf = _console()
    render.render_event(
        c, {"type": "tool_call", "payload": {"name": "calculate", "args": {"x": 1}}}
    )
    out = buf.getvalue()
    assert "calculate" in out


def test_tool_result_truncates_long_content():
    c, buf = _console()
    long = "A" * (render.RESULT_TRUNCATE_LIMIT + 200)
    render.render_event(c, {"type": "tool_result", "payload": {"name": "shell", "content": long}})
    out = buf.getvalue()
    assert "shell" in out
    assert "…" in out  # truncation marker present
    assert "A" * (render.RESULT_TRUNCATE_LIMIT + 200) not in out  # full content not shown


def test_error_event_is_displayed():
    c, buf = _console()
    render.render_event(c, {"type": "error", "payload": {"content": "boom failure"}})
    assert "boom failure" in buf.getvalue()


def test_approval_required_shows_prompt():
    c, buf = _console()
    render.render_event(
        c,
        {
            "type": "approval_required",
            "payload": {"approval_id": "a1", "tool": "shell", "risk": "high"},
        },
    )
    out = buf.getvalue()
    assert "a1" in out and "shell" in out


def test_render_status_writes_message():
    c, buf = _console()
    render.render_status(c, "connecting…")
    assert "connecting" in buf.getvalue()


def test_done_event_does_not_raise():
    c, _buf = _console()
    render.render_event(c, {"type": "done", "payload": {"content": "ok"}})
