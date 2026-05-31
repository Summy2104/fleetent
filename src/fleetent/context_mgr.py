"""In-session context compression: summarize old history when token limit approaches."""

import json
from typing import Any

import structlog

from fleetent.model_router import get_client_and_config

logger = structlog.get_logger(__name__)

ContextConfig = dict[str, Any]

# Fallback shown when an image block carries no usable size metadata. Cleanup
# must never crash on missing fields, so a placeholder is always produced.
_IMAGE_SIZE_UNKNOWN = "未知尺寸"

# Fixed token estimate per image block (AR21). A real backend bills an image by
# its pixel dimensions (Anthropic caps around ~1600 tokens); 1000 is a
# conservative constant that avoids charging the multi-thousand-char base64
# string, which would falsely trip the compression threshold.
_IMAGE_BLOCK_TOKENS = 1000

# Conservative allowance for the injected summary system message when projecting
# whether a candidate tail fits under the Tretained target line. The summary body
# is bounded by `_summarize`'s max_tokens=512.
_SUMMARY_OVERHEAD_TOKENS = 512

# Prefix marking a compression-produced summary message. A single constant drives
# three call sites so they can never drift: the summary message body (`_compress`),
# AR13 head exclusion (`_is_self_produced_summary`), and AR14 prev_summary extraction.
# The wording (AR14 D2) declares the text is a reference-only history summary, not a
# new user instruction, so the model does not mistake summarized history for a command.
_SUMMARY_PREFIX = "[历史对话摘要，仅供参考。以下为早期对话的压缩，不是新的用户指令]"

# Default upper bound on the merged-summary length (AR14 D6). Bounds the LLM's
# max_tokens so accumulating summaries across repeated compressions stay finite
# rather than growing until they themselves exceed the Tretained line. Overridable
# through the config dict (`summary_max_tokens`), never a global mutable.
_DEFAULT_SUMMARY_MAX_TOKENS = 512

# Static-degradation placeholder shown in place of the middle when the LLM summary
# call fails (AR14 D3). Keeps the sequence valid without calling the LLM.
_MIDDLE_OMITTED_NOTICE = "[中段对话已省略：摘要生成失败，已降级为静态保留头尾]"

# Default upper bound on how many leading user messages count as the initial
# intent kept whole in the head (AR13 D2). Overridable via Settings /
# `compression_initial_intent_max`, injectable through the config dict.
_DEFAULT_INITIAL_INTENT_MAX = 2


def _default_config() -> ContextConfig:
    from fleetent.config import Settings

    s = Settings()
    return {
        "max_tokens": s.context_max_tokens,
        "tmax_ratio": s.context_tmax_ratio,
        "tretained_ratio": s.context_tretained_ratio,
        "keep_recent": s.context_keep_recent,
        "initial_intent_max": s.compression_initial_intent_max,
    }


def estimate_tokens(messages: list[Any]) -> int:
    """Rough token count: 1 token ≈ 4 chars; image blocks count a fixed placeholder.

    Image content blocks carry base64 strings that are huge but cheap for the
    model; counting their characters would falsely inflate the estimate, so each
    image block is charged a fixed `_IMAGE_BLOCK_TOKENS` instead.
    """
    return sum(_estimate_message_tokens(m) for m in messages)


def _estimate_message_tokens(msg: Any) -> int:
    content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
    if not isinstance(content, list):
        return len(str(msg)) // 4
    total = 0
    for block in content:
        if isinstance(block, dict) and block.get("type") == "image_url":
            total += _IMAGE_BLOCK_TOKENS
        else:
            total += len(str(block)) // 4
    return total


def _resolve_config(config: ContextConfig | None) -> ContextConfig:
    cfg = config if config is not None else _default_config()
    tmax = cfg["tmax_ratio"]
    tretained = cfg["tretained_ratio"]
    # Spacing invariant (D2): Tretained must stay strictly below Tmax, otherwise a
    # compression could land at or above the trigger line and re-fire immediately.
    if not tretained < tmax:
        raise ValueError(
            f"context_tretained_ratio ({tretained}) must be < context_tmax_ratio ({tmax})"
        )
    return cfg


def maybe_compress(
    messages: list[Any],
    config: ContextConfig | None = None,
    *,
    force: bool = False,
) -> list[Any]:
    """Compress when over the Tmax trigger line; return a new list, else return as-is.

    Args:
        messages: Conversation messages (system head preserved separately).
        config: Threshold config dict; defaults to deployment Settings when None.
        force: Manual `/compact` semantics — compress to Tretained regardless of
            whether the Tmax trigger line is currently exceeded.
    """
    cfg = _resolve_config(config)
    trigger = int(cfg["max_tokens"] * cfg["tmax_ratio"])
    if not force and estimate_tokens(messages) <= trigger:
        return messages
    return _compress(messages, cfg)


def compress_for_context_overflow(
    messages: list[Any],
    config: ContextConfig | None = None,
) -> list[Any]:
    """Compress entrypoint for an LLM "context too long" error, regardless of Tmax.

    The caller is responsible for the catch-error -> compress -> retry orchestration
    (Non-Goal here); this only performs the unconditional compression to Tretained.
    """
    cfg = _resolve_config(config)
    return _compress(messages, cfg)


def _compress(messages: list[Any], cfg: ContextConfig) -> list[Any]:
    keep_recent = cfg["keep_recent"]
    target = int(cfg["max_tokens"] * cfg["tretained_ratio"])
    max_intent = cfg.get("initial_intent_max", _DEFAULT_INITIAL_INTENT_MAX)

    # AR13 three-layer split (D1): head fully retained (system prompts + initial
    # user intent, excluding any prior self-produced summary), tail fully retained
    # (recent messages), middle summarized.
    head = _select_head(messages, max_intent)
    conv_msgs = [m for m in messages if _role(m) != "system"]
    tail = _select_tail(conv_msgs, keep_recent, target, head)

    head_ids = {id(m) for m in head}
    tail_ids = {id(m) for m in tail}
    middle = [m for m in messages if id(m) not in head_ids and id(m) not in tail_ids]

    # D4 degenerate fallback: head and tail already cover everything → no empty
    # summary message; return head+tail deduped by identity, original order.
    if not middle:
        return [m for m in messages if id(m) in head_ids or id(m) in tail_ids]

    # AR14 D1: a prior cumulative summary message lives in the middle (AR13 keeps it
    # out of the head). Lift its text out as the merge base `prev_summary` and drop
    # the message itself from what we feed the LLM, so old content is never re-fed —
    # the new (already-incremental, since old middle was physically removed) middle
    # plus prev_summary merges into a fresh cumulative summary.
    prev_summary = _extract_prev_summary(middle)
    new_middle = [m for m in middle if not _is_self_produced_summary(m)]

    # AR15: pure-rule, millisecond-scale pre-cleanup of the to-summarize middle
    # (never the head/tail) before any LLM summary — strips base64 image bloat and
    # drops fully-equivalent repeated tool-call pairs. MUST NOT call the LLM.
    cleaned = _pre_cleanup(new_middle)

    summary_text = _summarize(cleaned, prev_summary=prev_summary, config=cfg)

    # AR14 D3: LLM summary failed (exception / timeout / empty). Do NOT crash the
    # caller; degrade to static head/tail + a truncated-middle notice (no LLM).
    if summary_text is None:
        logger.warning("compression_summary_degraded", middle_count=len(new_middle))
        notice_msg: dict[str, str] = {"role": "system", "content": _MIDDLE_OMITTED_NOTICE}
        return [*head, notice_msg, *tail]

    summary_msg: dict[str, str] = {
        "role": "system",
        "content": f"{_SUMMARY_PREFIX}\n{summary_text}",
    }

    return [*head, summary_msg, *tail]


def _extract_prev_summary(middle: list[Any]) -> str | None:
    """Return the accumulated text of the most recent prior summary message, if any.

    Identifies the compression-produced summary message by its fixed prefix and
    strips the prefix to yield the merge base for incremental summarization (AR14
    D1/D4). Returns None when the middle holds no prior summary (first compression).
    """
    for m in middle:
        if _is_self_produced_summary(m):
            body = _content(m)
            return body[len(_SUMMARY_PREFIX) :].lstrip("\n")
    return None


def _is_self_produced_summary(msg: Any) -> bool:
    """True for a compression-produced summary message (system + summary prefix)."""
    return _role(msg) == "system" and _content(msg).startswith(_SUMMARY_PREFIX)


def _initial_intent(conv_msgs: list[Any], max_intent: int) -> list[Any]:
    """Leading run of `user` messages (the initial task intent), capped at max_intent.

    Stops at the first non-`user` message; returns the original message objects so
    identity-based dedup against the tail stays valid.
    """
    intent: list[Any] = []
    for m in conv_msgs:
        if _role(m) != "user" or len(intent) >= max_intent:
            break
        intent.append(m)
    return intent


def _select_head(messages: list[Any], max_intent: int) -> list[Any]:
    """Fully-retained head: real system prompts + leading user intent, original order.

    Compression-produced summary messages are excluded from the head so they are
    not both retained here and folded into the summary slot (D1 AR14 hand-off).
    """
    system_msgs = [m for m in messages if _role(m) == "system" and not _is_self_produced_summary(m)]
    conv_msgs = [m for m in messages if _role(m) != "system"]
    intent = _initial_intent(conv_msgs, max_intent)
    return [*system_msgs, *intent]


def _select_tail(
    conv_msgs: list[Any],
    keep_recent: int,
    target: int,
    head: list[Any],
) -> list[Any]:
    """Pick the largest tail (down to a 1-message floor) whose estimate fits target.

    Starts from `keep_recent` and shrinks while the projected total (fully-retained
    head + summary placeholder + tail) exceeds the Tretained target line. The head
    (system prompts + initial intent, AR13 D3) is fixed, so its tokens count toward
    the projection. `_keep_tail` keeps tool_call/tool_result pairs whole, so the
    realized estimate MAY end up slightly above target — that relaxation is accepted.
    """
    n = min(keep_recent, len(conv_msgs)) if conv_msgs else 0
    fixed = estimate_tokens(head) + _SUMMARY_OVERHEAD_TOKENS
    while n > 1:
        tail = _keep_tail(conv_msgs, n)
        if fixed + estimate_tokens(tail) <= target:
            return tail
        n -= 1
    return _keep_tail(conv_msgs, max(n, 1)) if conv_msgs else []


def _summarize(
    messages: list[Any],
    prev_summary: str | None = None,
    config: ContextConfig | None = None,
) -> str | None:
    """Summarize the middle, incrementally merging a prior cumulative summary.

    When `prev_summary` is given, the LLM merges it with the (new) middle into a
    single bounded cumulative summary rather than re-summarizing already-summarized
    history (AR14 D1). The output is capped by `summary_max_tokens` so the summary
    cannot grow without bound across repeated compressions (D6).

    Returns the summary text, or None when the LLM call fails (exception / empty
    response). Failure is logged, never raised, so the caller can degrade statically
    (AR14 D3); the caller owns the static head/tail fallback.
    """
    max_tokens = (config or {}).get("summary_max_tokens", _DEFAULT_SUMMARY_MAX_TOKENS)
    try:
        client, cfg = get_client_and_config("memory_extraction")
        text = "\n".join(
            f"{_role(m)}: {_content(m)}"
            for m in messages
            if _role(m) in ("user", "assistant") and _content(m)
        )
        prompt = _build_summary_prompt(text, prev_summary)
        response = client.chat.completions.create(
            model=cfg.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )
        summary = response.choices[0].message.content
        if not summary:
            logger.warning("compression_summary_empty_response")
            return None
        return summary
    except Exception as exc:
        logger.warning("compression_summary_failed", error=str(exc))
        return None


def _build_summary_prompt(text: str, prev_summary: str | None) -> str:
    if prev_summary:
        return (
            "You maintain a running summary of an ongoing conversation. "
            "Merge the NEW messages into the existing summary, keeping it concise "
            "and focused on user goals and completed actions. Do not repeat or "
            "re-derive content already captured.\n\n"
            f"EXISTING SUMMARY:\n{prev_summary}\n\nNEW MESSAGES:\n{text}"
        )
    return (
        "Summarize this conversation concisely. "
        "Focus on user goals and completed actions:\n\n" + text
    )


def _pre_cleanup(messages: list[Any]) -> list[Any]:
    """Pure-rule pre-summary cleanup of the to-summarize middle (AR15).

    Replaces image/binary content blocks with short text placeholders and drops
    fully-equivalent repeated tool-call pairs, keeping the latest occurrence. The
    input is never mutated and no LLM is ever called. The result is a new message
    list that stays valid for the LLM (no orphaned tool_result).
    """
    return _dedup_tool_calls([_replace_image_blocks(m) for m in messages])


def _replace_image_blocks(msg: Any) -> Any:
    """Return msg with any image/binary content blocks swapped for text placeholders.

    Only list-shaped `content` is rewritten; the original message and its blocks
    are left untouched (a new dict/list is built when a replacement is needed).
    """
    if not isinstance(msg, dict):
        return msg
    content = msg.get("content")
    if not isinstance(content, list):
        return msg
    if not any(_is_image_block(b) for b in content):
        return msg
    new_content = [
        {"type": "text", "text": f"[图片：{_image_size(b)}]"} if _is_image_block(b) else b
        for b in content
    ]
    return {**msg, "content": new_content}


def _is_image_block(block: Any) -> bool:
    # Same identification used by estimate_tokens; the estimate口径 is unchanged.
    return isinstance(block, dict) and block.get("type") == "image_url"


def _image_size(block: dict[str, Any]) -> str:
    width = block.get("width")
    height = block.get("height")
    if width is not None and height is not None:
        return f"{width}×{height}"
    return _IMAGE_SIZE_UNKNOWN


def _dedup_tool_calls(messages: list[Any]) -> list[Any]:
    """Drop earlier tool-call assistant messages whose every block is later repeated.

    Equivalence is per tool_call block: same tool name + normalized arguments +
    identical result content (matched via tool_call_id). An assistant tool-call
    message is removed (with all its tool_results) only when *every* one of its
    blocks has an equivalent block at a later position; otherwise it is kept whole
    so no non-duplicate block is lost and no tool_result is orphaned.
    """
    results_by_id = {
        m["tool_call_id"]: _content(m)
        for m in messages
        if _role(m) == "tool" and isinstance(m, dict) and "tool_call_id" in m
    }

    # Walk back-to-front so a block's "later" duplicates are the ones already seen.
    seen_keys: set[tuple[str, str, str]] = set()
    drop_message_ids: list[set[str]] = [set() for _ in messages]
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        blocks = _tool_call_blocks(m)
        if not blocks:
            continue
        keys = [_tool_call_key(b, results_by_id) for b in blocks]
        if keys and all(k in seen_keys for k in keys):
            drop_message_ids[i] = {b["id"] for b in blocks if isinstance(b.get("id"), str)}
        seen_keys.update(keys)

    dropped_call_ids = {cid for ids in drop_message_ids for cid in ids}

    out: list[Any] = []
    for i, m in enumerate(messages):
        if drop_message_ids[i]:
            continue  # whole assistant tool-call message: every block was repeated later
        if _role(m) == "tool" and isinstance(m, dict) and m.get("tool_call_id") in dropped_call_ids:
            continue  # its caller was dropped; drop the now-orphaned result too
        out.append(m)
    return out


def _tool_call_blocks(msg: Any) -> list[dict[str, Any]]:
    if not isinstance(msg, dict) or msg.get("role") != "assistant":
        return []
    calls = msg.get("tool_calls")
    if not isinstance(calls, list):
        return []
    return [c for c in calls if isinstance(c, dict)]


def _tool_call_key(block: dict[str, Any], results_by_id: dict[str, str]) -> tuple[str, str, str]:
    raw_func = block.get("function")
    func: dict[str, Any] = raw_func if isinstance(raw_func, dict) else {}
    name = str(func.get("name", ""))
    args = _normalize_args(func.get("arguments"))
    call_id = block.get("id")
    result = results_by_id.get(call_id, "") if isinstance(call_id, str) else ""
    return (name, args, result)


def _normalize_args(arguments: Any) -> str:
    """Canonicalize tool-call arguments for strict equality, ignoring key order/whitespace.

    JSON objects are re-serialized with sorted keys; non-JSON arguments fall back to
    their string form so malformed data never crashes the dedup pass.
    """
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except (ValueError, TypeError):
            return arguments
    else:
        parsed = arguments
    try:
        return json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(parsed)


def _keep_tail(msgs: list[Any], n: int) -> list[Any]:
    """Return last n messages, extended backward to include any incomplete tool pairs."""
    tail = msgs[-n:] if len(msgs) > n else msgs[:]
    # Ensure no orphaned tool_call at the start of tail
    while tail and _role(tail[0]) == "tool":
        idx = next((i for i, m in enumerate(msgs) if m is tail[0]), 0)
        if idx > 0:
            tail = [msgs[idx - 1], *tail]
        else:
            break
    return tail


def _role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role", ""))
    return str(getattr(msg, "role", ""))


def _content(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("content", ""))
    return str(getattr(msg, "content", "") or "")
