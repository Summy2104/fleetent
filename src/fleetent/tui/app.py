"""TUI main loop entry point (fleetent-tui).

``AppController`` holds the testable interaction logic — a submitted line becomes a
backend action (chat → ``send``; slash command → abort/approve/session/quit/help),
and gateway events render to the terminal. Rendering goes through an injectable
``emit`` sink (default: prompt_toolkit ``print_formatted_text``), which is
patch_stdout-safe; ``run`` wires it to a ``PromptSession`` running concurrently
with the backend's receive loop under ``patch_stdout`` so streamed output and the
input line coexist. ``main`` parses ``--url``/``--token`` and starts the loop.
"""

import argparse
import asyncio
import os
from collections.abc import Callable
from typing import Any, Protocol

from prompt_toolkit import PromptSession, print_formatted_text
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.patch_stdout import patch_stdout

from fleetent.observability.structured_logging import get_logger
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
        """Render a gateway event; clear the active run on a terminal event."""
        rendered = render.format_event(event)
        if rendered is not None:
            self._emit(rendered, "")  # newlines are baked into the rendered text
        if event.get("type") in (p.EVENT_DONE, p.EVENT_ERROR):
            self.current_run_id = None

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


def main() -> None:
    parser = argparse.ArgumentParser(prog="fleetent-tui", description="fleetent terminal TUI")
    parser.add_argument("--url", default=os.environ.get("FLEETENT_TUI_URL", DEFAULT_URL))
    parser.add_argument("--token", default=os.environ.get("FLEETENT_TOKEN", ""))
    args = parser.parse_args()
    if not args.token:
        parser.error("a Bearer ma- key is required via --token or FLEETENT_TOKEN")
    asyncio.run(_run(args.url, args.token))
