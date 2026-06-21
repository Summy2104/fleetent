"""Slash-command parsing + prompt_toolkit completer.

Lines beginning with ``/`` are commands (``/new /session /abort /approve /quit
/help``); anything else is a chat message. Parsing is a pure function so it is
trivially unit-testable; ``SlashCommandCompleter`` offers completion in the input.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

KNOWN_COMMANDS = frozenset({"new", "session", "abort", "approve", "quit", "help", "user"})


@dataclass(frozen=True)
class Command:
    name: str
    args: list[str]


def parse_command(text: str) -> Command | None:
    """Parse a ``/command [args...]`` line; return ``None`` for plain chat input."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    parts = stripped[1:].split()
    if not parts:
        return None
    return Command(name=parts[0], args=parts[1:])


class SlashCommandCompleter(Completer):
    """Complete known slash commands when the line starts with ``/``."""

    def get_completions(self, document: Document, complete_event: object) -> Iterable[Completion]:
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        prefix = text[1:]
        for name in sorted(KNOWN_COMMANDS):
            if name.startswith(prefix):
                yield Completion(name, start_position=-len(prefix))
