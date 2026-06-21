"""TUI main loop entry point (fleetent chat).

``AppController`` holds the testable interaction logic — a submitted line becomes a
backend action (chat → ``send``; slash command → abort/approve/session/quit/help),
and gateway events render to the terminal. Rendering goes through an injectable
``emit`` sink (default: ``print_formatted_text`` via ``run_in_terminal`` while the
prompt runs, so output is committed above the live input line instead of erased by
the prompt's next repaint). Streamed ``text_delta`` is buffered and emitted only as
complete lines, because a partial (newline-less) line isn't committed to scrollback
and would flash then disappear. ``run`` drives a ``PromptSession`` concurrently with
the backend's receive loop under ``patch_stdout`` (which catches stray writes).
``main`` parses ``--url``/``--token`` and starts the loop.
"""

import argparse
import asyncio
import os
from collections.abc import Callable
from typing import Any, Protocol

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.application import get_app_or_none, run_in_terminal
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.patch_stdout import patch_stdout

from fleetent.structured_logging import get_logger
from fleetent.tui import protocol as p
from fleetent.tui import render
from fleetent.tui.backend import GatewayBackend
from fleetent.tui.commands import KNOWN_COMMANDS, SlashCommandCompleter, parse_command

_logger = get_logger("tui.app")

DEFAULT_URL = "ws://127.0.0.1:8765/ws"
_HELP = "commands: /new /session /abort [run_id] /approve <id> <approved|rejected> /quit /help"

# A sink that prints rendered FormattedText; ``end`` lets streaming text stay inline.
EmitFn = Callable[[FormattedText, str], None]


def _default_emit(text: FormattedText, end: str) -> None:
    # While the PromptSession app is running it owns the bottom of the screen and
    # repaints it; a plain print lands in that region and the next repaint erases it
    # ("flashes then disappears"). run_in_terminal suspends the app, prints above the
    # prompt (committed to scrollback), then redraws — so streamed output persists.
    app = get_app_or_none()
    if app is not None and app.is_running:
        run_in_terminal(lambda: print_formatted_text(text, end=end))
    else:
        print_formatted_text(text, end=end)


class Backend(Protocol):
    """The subset of the gateway backend the controller drives."""

    async def send(self, message: str, session_id: str | None = None) -> dict[str, Any]: ...
    async def abort(self, run_id: str) -> dict[str, Any]: ...
    async def approve(self, approval_id: str, decision: str) -> dict[str, Any]: ...
    async def session_new(self) -> dict[str, Any]: ...
    async def session_list(self) -> dict[str, Any]: ...


class AppController:
    """Interaction logic: input line → backend action; gateway event → render."""

    def __init__(
        self, backend: Backend, emit: EmitFn | None = None, session_id: str | None = None
    ) -> None:
        self.backend = backend
        self._emit = emit or _default_emit
        self.session_id = session_id
        self.current_run_id: str | None = None
        # Streamed text_delta content accumulates here until a newline / a structured
        # event / done, then is emitted as a COMPLETE line. Partial (newline-less)
        # output isn't committed to the terminal scrollback and the prompt's repaint
        # erases it ("flashes then disappears"), so we only ever emit whole lines.
        self._text_buf = ""

    def _status(self, message: str) -> None:
        self._emit(render.format_status(message), "\n")

    async def handle_line(self, text: str) -> bool:
        """Process one submitted line; return ``False`` to quit the loop."""
        cmd = parse_command(text)
        if cmd is None:
            if text.strip():
                result = await self.backend.send(text, session_id=self.session_id)
                self.current_run_id = result.get("run_id")
            return True

        if cmd.name == "quit":
            return False
        if cmd.name == "help":
            self._status(_HELP)
            return True
        if cmd.name == "new":
            result = await self.backend.session_new()
            self.session_id = result.get("session_id")
            self._status(f"new session: {self.session_id}")
            return True
        if cmd.name == "session":
            result = await self.backend.session_list()
            self._status(f"sessions: {result.get('sessions', [])}")
            return True
        if cmd.name == "abort":
            run_id = cmd.args[0] if cmd.args else self.current_run_id
            if run_id:
                await self.backend.abort(run_id)
            else:
                self._status("no active run to abort")
            return True
        if cmd.name == "approve":
            if len(cmd.args) >= 2:
                await self.backend.approve(cmd.args[0], cmd.args[1])
            else:
                self._status("usage: /approve <id> <approved|rejected>")
            return True

        # Known commands are handled above; anything else is unknown.
        if cmd.name not in KNOWN_COMMANDS:
            self._status(f"unknown command: /{cmd.name}")
        return True

    def on_event(self, event: dict[str, Any]) -> None:
        """Render a gateway event.

        Streamed ``text_delta`` accumulates and is emitted only as complete lines
        (see ``_text_buf``); every other event first flushes any pending text, then
        renders. Terminal events (``done``/``error``) clear the active run.
        """
        event_type = event.get("type", "")
        if event_type == p.EVENT_TEXT_DELTA:
            payload = event.get("payload", {}) or {}
            self._text_buf += str(payload.get("content", ""))
            self._flush_complete_lines()
            return
        self._flush_text(final=True)  # close any open streamed line before other output
        if event_type != p.EVENT_DONE:  # done carries no renderable content
            rendered = render.format_event(event)
            if rendered is not None:
                self._emit(rendered, "")
        if event_type in (p.EVENT_DONE, p.EVENT_ERROR):
            self.current_run_id = None

    def _flush_complete_lines(self) -> None:
        """Emit any whole (newline-terminated) lines now; keep the trailing partial."""
        if "\n" not in self._text_buf:
            return
        head, _, tail = self._text_buf.rpartition("\n")
        self._emit(FormattedText([("", head + "\n")]), "")
        self._text_buf = tail

    def _flush_text(self, final: bool = False) -> None:
        """Flush buffered streamed text. With ``final`` the trailing partial is closed
        with a newline (a structured event or done is about to print on its own line)."""
        self._flush_complete_lines()
        if final and self._text_buf:
            self._emit(FormattedText([("", self._text_buf + "\n")]), "")
            self._text_buf = ""

    async def interrupt(self) -> None:
        """Ctrl-C: abort the in-flight run, if any."""
        if self.current_run_id:
            await self.backend.abort(self.current_run_id)

    async def run(self) -> None:
        """Prompt loop: read lines under patch_stdout until the user quits."""
        session: PromptSession[str] = PromptSession(completer=SlashCommandCompleter())
        with patch_stdout():
            while True:
                try:
                    text = await session.prompt_async("› ")
                except (EOFError, KeyboardInterrupt):
                    await self.interrupt()
                    break
                if not await self.handle_line(text):
                    break


async def _run(url: str, token: str) -> None:
    controller = AppController(backend=None)  # type: ignore[arg-type]
    backend = GatewayBackend(url, token, on_event=controller.on_event)
    controller.backend = backend
    controller._status(f"connecting to {url} …")
    await backend.connect()
    controller._status("connected. type a message, or /help.")
    try:
        await controller.run()
    finally:
        await backend.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fleetent chat", description="fleetent terminal TUI")
    parser.add_argument("--url", default=os.environ.get("FLEETENT_TUI_URL", DEFAULT_URL))
    parser.add_argument("--token", default=os.environ.get("FLEETENT_TOKEN", ""))
    args = parser.parse_args(argv)
    if not args.token:
        parser.error("a Bearer ma- key is required via --token or FLEETENT_TOKEN")
    asyncio.run(_run(args.url, args.token))
