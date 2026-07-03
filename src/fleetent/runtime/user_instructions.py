"""Per-agent ``user.md``: explicit, user-editable directives for one agent.

Stored at ``agents/<agent_name>/user.md`` (alongside ``agent.yaml``) and injected
into the system-prompt *stable prefix* — distinct from the implicit ``memory/``
layer. Per-agent shared (every user of an agent sees the same directives). Read
fresh each turn via ``paths.agent_home_dir`` (evaluated at call time), so it never
goes through ``AgentConfigIndex`` caching and a write is visible on the next turn.

The ``/user`` command (view / append / clear) is implemented once here and wired
by every entrypoint (CLI / Slack / Telegram / TUI); none of these operations ever
touch a platform table.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from fleetent import paths
from fleetent.structured_logging import get_logger

_logger = get_logger("runtime.user_instructions")

USER_MD_FILENAME = "user.md"

# Injection-side cap on the directives folded into the cacheable prefix; the disk
# original is never rewritten by truncation (aligns with hermes USER.md scale).
_MAX_CHARS = 4000
_TRUNCATION_MARKER = "\n…[用户指令已截断]"

_COMMAND = "/user"
_CLEAR_ARG = "clear"


def _path(agent_name: str) -> Path:
    return paths.agent_home_dir(agent_name) / USER_MD_FILENAME


def _read_raw(agent_name: str) -> str:
    """Return the full on-disk ``user.md`` text, or ``""`` when absent/unreadable."""
    path = _path(agent_name)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        _logger.warn("user_md_read_failed", agent_name=agent_name, exception=exc)
        return ""


def _atomic_write(path: Path, text: str) -> None:
    """Persist ``text`` via ``tmp → replace`` (mirrors session/manager atomic write)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def load(agent_name: str) -> str:
    """Return ``user.md`` for prompt injection, truncated to ``_MAX_CHARS``.

    Missing file yields ``""``. Truncation appends a visible marker and never
    rewrites the on-disk original.
    """
    text = _read_raw(agent_name).strip()
    if len(text) > _MAX_CHARS:
        return text[:_MAX_CHARS] + _TRUNCATION_MARKER
    return text


def append(agent_name: str, content: str) -> None:
    """Append one directive line to ``user.md`` atomically."""
    line = content.strip()
    if not line:
        return
    existing = _read_raw(agent_name).rstrip("\n")
    new_text = f"{existing}\n{line}\n" if existing.strip() else f"{line}\n"
    _atomic_write(_path(agent_name), new_text)


def clear(agent_name: str) -> None:
    """Remove ``user.md`` if present. Idempotent."""
    with suppress(FileNotFoundError):
        _path(agent_name).unlink()


def handle_user_command(agent_name: str, text: str) -> str | None:
    """Handle a ``/user [...]`` command; return a reply, or ``None`` if not a command.

    ``None`` means the text is ordinary chat and should proceed to the agent loop.
    A non-``None`` return is the user-facing receipt and the input MUST NOT run the
    loop. Sub-commands: bare ``/user`` views, ``/user clear`` clears, ``/user <x>``
    appends.
    """
    stripped = (text or "").strip()
    if stripped == _COMMAND:
        arg = ""
    elif stripped.startswith(_COMMAND + " "):
        arg = stripped[len(_COMMAND) :].strip()
    else:
        return None

    if not arg:
        current = _read_raw(agent_name).strip()
        return current if current else "尚未设置用户指令。用 `/user <内容>` 添加。"
    if arg == _CLEAR_ARG:
        clear(agent_name)
        return "已清空用户指令。"
    append(agent_name, arg)
    return f"已追加用户指令：{arg}"
