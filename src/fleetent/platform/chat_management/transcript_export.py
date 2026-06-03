"""Pure rendering of a session transcript to Markdown for export.

No IO — the caller fetches the transcript through the session seam and passes it in.
"""

from typing import Any


def render_markdown(session_id: str, transcript: list[dict[str, Any]]) -> str:
    """Render a transcript as a Markdown document headed by the session id."""
    lines = [f"# Session {session_id}", ""]
    for msg in transcript:
        role = str(msg.get("role", "unknown"))
        content = str(msg.get("content", ""))
        lines.append(f"**{role}**")
        lines.append("")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)
