"""Tool result truncation with spillover file support (T4 / tool-result-truncation spec).

Strategy:
- Results ≤ MAX_TOOL_RESULT_BYTES: returned unchanged.
- Results > MAX_TOOL_RESULT_BYTES:
    - Normal tools: write full content to a spillover file under SPILLOVER_DIR,
      return the first SPILLOVER_PREVIEW_LINES lines as preview plus the file
      path and a read_file hint so the agent can continue reading.
    - Self-truncating tools (run_code, bash_exec): legacy head+tail+breadcrumb
      path — they already cap their own streams; this is a last-resort safety cap.

All byte measurements use UTF-8 encoding, consistent with SB6.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from fleetent import paths

# ~12.5k tokens at ~4 bytes/token. Module-level → injectable for tests.
MAX_TOOL_RESULT_BYTES = 50_000

# Lines to include in the spillover preview returned to the LLM.
SPILLOVER_PREVIEW_LINES = 100

# Directory for spillover files. Injectable via monkeypatch in tests.
SPILLOVER_DIR: Path = paths.data_dir() / "tool_spillover"

_BREADCRUMB = "[...工具结果已截断：原始 {orig} 字节，省略中间 {omitted} 字节...]"

_SPILLOVER_HINT = (
    "\n[...结果过大（{orig_kb:.1f} KB），已截断至前 {lines} 行。"
    "完整内容保存于：{path}\n"
    "可用 read_file(path='{path}', offset={next_offset}) 继续读取...]"
)


def truncate_tool_result(
    result: str,
    max_bytes: int | None = None,
    self_truncates: bool = False,
) -> str:
    """Return result capped to max_bytes, using spillover for normal tools.

    Args:
        result: The raw tool output string.
        max_bytes: Override the module-level threshold (used in tests).
        self_truncates: When True, use the legacy head+tail+breadcrumb strategy
            instead of writing a spillover file. Set for tools like run_code and
            bash_exec that already cap their own output streams.
    """
    limit = MAX_TOOL_RESULT_BYTES if max_bytes is None else max_bytes
    orig = len(result.encode("utf-8"))
    if orig <= limit:
        return result

    if self_truncates:
        return _head_tail_breadcrumb(result, limit, orig)

    return _spillover(result, orig, limit)


def _spillover(result: str, orig: int, limit: int) -> str:
    """Write full content to a spillover file; return preview + path + hint.

    The combined preview+hint is guaranteed not to exceed limit bytes via a
    final safety truncation (covers artificially small limits in tests and
    edge cases where individual lines are unusually long).
    """
    SPILLOVER_DIR.mkdir(parents=True, exist_ok=True)
    spill_path = SPILLOVER_DIR / f"{uuid.uuid4().hex}.txt"
    spill_path.write_text(result, encoding="utf-8")

    lines = result.splitlines()
    preview_lines = lines[:SPILLOVER_PREVIEW_LINES]
    preview = "\n".join(preview_lines)
    next_offset = SPILLOVER_PREVIEW_LINES + 1

    hint = _SPILLOVER_HINT.format(
        orig_kb=orig / 1024,
        lines=min(SPILLOVER_PREVIEW_LINES, len(lines)),
        path=str(spill_path),
        next_offset=next_offset,
    )
    combined = preview + hint
    combined_bytes = len(combined.encode("utf-8"))
    if combined_bytes > limit:
        return _head_tail_breadcrumb(combined, limit, combined_bytes)
    return combined


def _head_tail_breadcrumb(result: str, limit: int, orig: int) -> str:
    """Legacy head+tail truncation for self-truncating tools."""
    reserve = len(_BREADCRUMB.format(orig=orig, omitted=orig).encode("utf-8"))
    content_budget = max(0, limit - reserve)
    head_budget = content_budget // 2
    tail_budget = content_budget - head_budget

    head = _head_bytes(result, head_budget)
    tail = _tail_bytes(result, tail_budget)
    omitted = orig - len(head.encode("utf-8")) - len(tail.encode("utf-8"))
    return head + _BREADCRUMB.format(orig=orig, omitted=omitted) + tail


def cleanup_spillover(
    spillover_dir: Path | None = None,
    max_age_days: int = 7,
) -> None:
    """Delete spillover files older than max_age_days. Safe to call if dir absent."""
    target = spillover_dir if spillover_dir is not None else SPILLOVER_DIR
    if not target.exists():
        return
    cutoff = time.time() - max_age_days * 86400
    for f in target.iterdir():
        if f.is_file() and os.path.getmtime(f) < cutoff:
            f.unlink(missing_ok=True)


def _head_bytes(s: str, n: int) -> str:
    """Longest prefix of s that fits in n UTF-8 bytes, on a char boundary."""
    chunk = s.encode("utf-8")[:n]
    while chunk:
        try:
            return chunk.decode("utf-8")
        except UnicodeDecodeError:
            chunk = chunk[:-1]
    return ""


def _tail_bytes(s: str, n: int) -> str:
    """Longest suffix of s that fits in n UTF-8 bytes, on a char boundary."""
    if n <= 0:
        return ""
    chunk = s.encode("utf-8")[-n:]
    while chunk:
        try:
            return chunk.decode("utf-8")
        except UnicodeDecodeError:
            chunk = chunk[1:]
    return ""
