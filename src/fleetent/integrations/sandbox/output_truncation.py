"""Truncate sandbox stdout/stderr before returning to the AI (SB6).

`run_code` output is capped on the assembly side (not inside SandboxClient.exec,
whose ExecResult still feeds the trace at original size). stdout and stderr have
separate byte budgets (sandbox.md: 50KB / 10KB) since they differ in nature.
Head + tail are preserved with a single-line truncation notice. Byte budget uses
`len(s.encode("utf-8"))`, consistent with the trace and T4. No LLM, no I/O.
"""

from __future__ import annotations

# Separate per-stream budgets (sandbox.md). Module-level → injectable in tests.
MAX_STDOUT_BYTES = 50 * 1024
MAX_STDERR_BYTES = 10 * 1024

_NOTICE = "[...沙箱输出已截断：原始 {orig} 字节，省略中间 {omitted} 字节...]"


def truncate_stream(text: str, max_bytes: int | None = None) -> str:
    """Return `text` capped to `max_bytes` UTF-8 bytes, head+tail+notice.

    Within budget → returned unchanged. The result never exceeds the budget and
    cuts always land on full UTF-8 character boundaries. `max_bytes` defaults to
    the stdout budget; callers pass the per-stream constant explicitly.
    """
    limit = MAX_STDOUT_BYTES if max_bytes is None else max_bytes
    orig = len(text.encode("utf-8"))
    if orig <= limit:
        return text

    reserve = len(_NOTICE.format(orig=orig, omitted=orig).encode("utf-8"))
    content_budget = max(0, limit - reserve)
    head_budget = content_budget // 2
    tail_budget = content_budget - head_budget

    head = _head_bytes(text, head_budget)
    tail = _tail_bytes(text, tail_budget)
    omitted = orig - len(head.encode("utf-8")) - len(tail.encode("utf-8"))
    return head + _NOTICE.format(orig=orig, omitted=omitted) + tail


def _head_bytes(s: str, n: int) -> str:
    chunk = s.encode("utf-8")[:n]
    while chunk:
        try:
            return chunk.decode("utf-8")
        except UnicodeDecodeError:
            chunk = chunk[:-1]
    return ""


def _tail_bytes(s: str, n: int) -> str:
    if n <= 0:
        return ""
    chunk = s.encode("utf-8")[-n:]
    while chunk:
        try:
            return chunk.decode("utf-8")
        except UnicodeDecodeError:
            chunk = chunk[1:]
    return ""
