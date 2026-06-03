"""rich-based terminal rendering of event notifications.

Pure rendering: every function takes an injectable ``rich.Console`` and writes to
it, so output can be captured in tests (``Console(file=StringIO)``). The renderer
maps a gateway ``event`` (``{type, payload, run_id?}``) to terminal output —
streaming text, tool-call/result panels, errors, approval prompts, status lines.
"""

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from fleetent.tui import protocol as p

# Tool results can be large (file dumps, shell output); show a head + a truncation
# marker rather than flooding the terminal.
RESULT_TRUNCATE_LIMIT = 800


def _truncate(text: str, limit: int = RESULT_TRUNCATE_LIMIT) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def render_event(console: Console, event: dict[str, Any]) -> None:
    """Render one gateway event (``{type, payload, ...}``) to the console."""
    event_type = event.get("type", "")
    payload = event.get("payload", {}) or {}

    if event_type == p.EVENT_TEXT_DELTA:
        console.print(str(payload.get("content", "")), end="", soft_wrap=True)
    elif event_type == p.EVENT_TOOL_CALL:
        name = str(payload.get("name", "?"))
        args = payload.get("args", {})
        console.print(Panel(Text(str(args)), title=f"🔧 {name}", border_style="cyan"))
    elif event_type == p.EVENT_TOOL_RESULT:
        name = str(payload.get("name", "?"))
        content = _truncate(str(payload.get("content", "")))
        console.print(Panel(Text(content), title=f"← {name}", border_style="green"))
    elif event_type == p.EVENT_ERROR:
        console.print(Text(f"error: {payload.get('content', '')}", style="bold red"))
    elif event_type == p.EVENT_APPROVAL_REQUIRED:
        tool = payload.get("tool", "?")
        risk = payload.get("risk", "?")
        approval_id = payload.get("approval_id", "?")
        console.print(
            Panel(
                Text(f"tool={tool} risk={risk}\n/approve {approval_id} approved|rejected"),
                title=f"⚠ approval required [{approval_id}]",
                border_style="yellow",
            )
        )
    elif event_type == p.EVENT_DONE:
        console.print()  # close the streamed line


def render_status(console: Console, message: str) -> None:
    """Render a dim status line (connection state, spinner text, etc.)."""
    console.print(Text(message, style="dim"))
