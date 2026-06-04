"""Source-side truncation of oversized tool results before they hit `messages` (T4).

A single pure function caps any (non self-truncating) tool result at a byte
budget before it is written to the message history, so one runaway tool result
cannot blow up the context. Head + tail are preserved with a breadcrumb naming
the original and omitted byte counts. Byte budget uses `len(s.encode("utf-8"))`,
consistent with SB6. No LLM, no I/O — millisecond, deterministic.
"""

from __future__ import annotations

# ~10k tokens at ~4 bytes/token. General cap for all tools except those that
# declare self_truncates (e.g. run_code, capped by SB6). Module-level → injectable.
MAX_TOOL_RESULT_BYTES = 40_000

_BREADCRUMB = "[...工具结果已截断：原始 {orig} 字节，省略中间 {omitted} 字节...]"


def truncate_tool_result(result: str, max_bytes: int | None = None) -> str:
    """Return `result` capped to `max_bytes` UTF-8 bytes, head+tail+breadcrumb.

    Within budget → returned unchanged. The returned string's UTF-8 byte length
    never exceeds the budget, and cuts always land on full character boundaries.
    """
    limit = MAX_TOOL_RESULT_BYTES if max_bytes is None else max_bytes
    orig = len(result.encode("utf-8"))
    if orig <= limit:
        return result

    # Reserve breadcrumb space with an upper bound on its byte length (omitted <=
    # orig, so its digit count can't exceed orig's), then split the remainder.
    reserve = len(_BREADCRUMB.format(orig=orig, omitted=orig).encode("utf-8"))
    content_budget = max(0, limit - reserve)
    head_budget = content_budget // 2
    tail_budget = content_budget - head_budget

    head = _head_bytes(result, head_budget)
    tail = _tail_bytes(result, tail_budget)
    omitted = orig - len(head.encode("utf-8")) - len(tail.encode("utf-8"))
    return head + _BREADCRUMB.format(orig=orig, omitted=omitted) + tail


def _head_bytes(s: str, n: int) -> str:
    """Longest prefix of `s` that fits in `n` UTF-8 bytes, on a char boundary."""
    chunk = s.encode("utf-8")[:n]
    while chunk:
        try:
            return chunk.decode("utf-8")
        except UnicodeDecodeError:
            chunk = chunk[:-1]  # back off a partial trailing multibyte char
    return ""


def _tail_bytes(s: str, n: int) -> str:
    """Longest suffix of `s` that fits in `n` UTF-8 bytes, on a char boundary."""
    if n <= 0:
        return ""
    chunk = s.encode("utf-8")[-n:]
    while chunk:
        try:
            return chunk.decode("utf-8")
        except UnicodeDecodeError:
            chunk = chunk[1:]  # back off a partial leading multibyte char
    return ""
