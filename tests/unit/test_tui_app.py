"""TUI app controller: input → backend actions, event → render, interrupt (tui-gateway 8.3)."""

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.shortcuts import PromptSession

from fleetent.tui import protocol as p
from fleetent.tui.app import AppController


class FakeBackend:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def send(self, message, session_id=None):
        self.calls.append(("send", message, session_id))
        return {"run_id": "r1"}

    async def abort(self, run_id):
        self.calls.append(("abort", run_id))
        return {"ok": True}

    async def approve(self, approval_id, decision):
        self.calls.append(("approve", approval_id, decision))
        return {"ok": True}

    async def session_new(self):
        self.calls.append(("session_new",))
        return {"session_id": "tui:u1:new"}

    async def session_list(self):
        self.calls.append(("session_list",))
        return {"sessions": ["tui:u1:a"]}


def _controller() -> tuple[AppController, FakeBackend, list[str]]:
    backend = FakeBackend()
    emitted: list[str] = []

    def emit(ft: FormattedText, end: str) -> None:
        emitted.append("".join(text for _s, text in ft) + end)

    return AppController(backend=backend, emit=emit), backend, emitted


async def test_plain_text_triggers_send_and_tracks_run():
    ctrl, backend, _ = _controller()
    cont = await ctrl.handle_line("hello agent")
    assert cont is True
    assert backend.calls[0] == ("send", "hello agent", ctrl.session_id)
    assert ctrl.current_run_id == "r1"


async def test_slash_abort_with_arg_and_without():
    ctrl, backend, _ = _controller()
    await ctrl.handle_line("/abort r9")
    assert ("abort", "r9") in backend.calls
    ctrl.current_run_id = "rcur"
    await ctrl.handle_line("/abort")
    assert ("abort", "rcur") in backend.calls


async def test_slash_approve_routes():
    ctrl, backend, _ = _controller()
    await ctrl.handle_line("/approve a1 approved")
    assert ("approve", "a1", "approved") in backend.calls


async def test_slash_new_and_session():
    ctrl, backend, _ = _controller()
    await ctrl.handle_line("/new")
    await ctrl.handle_line("/session")
    assert ("session_new",) in backend.calls
    assert ("session_list",) in backend.calls


async def test_slash_quit_returns_false():
    ctrl, _backend, _ = _controller()
    assert await ctrl.handle_line("/quit") is False


async def test_slash_help_renders_without_backend_call():
    ctrl, backend, emitted = _controller()
    cont = await ctrl.handle_line("/help")
    assert cont is True
    assert backend.calls == []
    assert any("/abort" in s for s in emitted)


async def test_unknown_command_renders_hint():
    ctrl, backend, emitted = _controller()
    await ctrl.handle_line("/frobnicate")
    assert backend.calls == []
    assert any("frobnicate" in s for s in emitted)


async def test_on_event_renders_and_clears_run_on_done():
    ctrl, _backend, emitted = _controller()
    ctrl.current_run_id = "r1"
    ctrl.on_event(p.make_event(p.EVENT_TEXT_DELTA, {"content": "streamed"}, run_id="r1")["params"])
    assert any("streamed" in s for s in emitted)
    ctrl.on_event(p.make_event(p.EVENT_DONE, {"content": ""}, run_id="r1")["params"])
    assert ctrl.current_run_id is None


async def test_interrupt_aborts_current_run():
    ctrl, backend, _ = _controller()
    ctrl.current_run_id = "rX"
    await ctrl.interrupt()
    assert ("abort", "rX") in backend.calls


async def test_promptsession_reads_a_line_via_pipe_input():
    with create_pipe_input() as inp:
        inp.send_text("a line\n")
        session: PromptSession = PromptSession(input=inp, output=DummyOutput())
        result = await session.prompt_async()
    assert result == "a line"
