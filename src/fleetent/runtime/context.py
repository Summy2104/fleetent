"""In-session context compression: summarize old history when token limit approaches."""

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, replace
from typing import Any, cast

from openai import OpenAI

from fleetent import eval_logger
from fleetent.model import ModelConfigError, ModelPolicySnapshot, ResolvedModelConfig
from fleetent.observability.structured_logging import get_logger
from fleetent.user_store import DB_PATH as DB_PATH  # noqa: F401 — re-export for monkeypatch

_DEFAULT_FLAP_WINDOW = 3
_DEFAULT_MIN_SAVINGS_RATIO = 0.10
_DEFAULT_MIN_INTERVAL_TURNS = 1

_logger = get_logger("runtime.context")

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


def _default_config(agent_name: str | None = None) -> ContextConfig:
    """Compression config: the named agent's context_* fields when resolvable, else
    a neutral default agent's schema defaults."""
    from fleetent import agent_config

    agent = agent_config.current().get(agent_name) if agent_name is not None else None
    if agent is None:
        agent = agent_config.active_agent_or_default()
    return {
        "max_tokens": agent.context_max_tokens,
        "tmax_ratio": agent.context_tmax_ratio,
        "tretained_ratio": agent.context_tretained_ratio,
        "keep_recent": agent.context_keep_recent,
        "initial_intent_max": agent.compression_initial_intent_max,
        "flap_window": agent.context_flap_window,
        "min_savings_ratio": agent.context_min_savings_ratio,
        "min_interval_turns": agent.context_min_interval_turns,
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


def _resolve_config(config: ContextConfig | None, agent_name: str | None = None) -> ContextConfig:
    cfg = config if config is not None else _default_config(agent_name)
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
    session_id: str | None = None,
    user_id: str | None = None,
    agent_name: str | None = None,
) -> list[Any]:
    """Compress when over the Tmax trigger line; return a new list, else return as-is.

    Args:
        messages: Conversation messages (system head preserved separately).
        config: Threshold config dict; defaults to deployment Settings when None.
        force: Manual `/compact` semantics — compress to Tretained regardless of
            whether the Tmax trigger line is currently exceeded.
    """
    cfg = _resolve_config(config, agent_name)
    trigger_line = int(cfg["max_tokens"] * cfg["tmax_ratio"])
    if not force and estimate_tokens(messages) <= trigger_line:
        return messages
    return _compress(
        messages,
        cfg,
        trigger="manual" if force else "tmax",
        session_id=session_id,
        user_id=user_id,
        agent_name=agent_name,
    )


def compress_for_context_overflow(
    messages: list[Any],
    config: ContextConfig | None = None,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    agent_name: str | None = None,
) -> list[Any]:
    """Compress entrypoint for an LLM "context too long" error, regardless of Tmax.

    The caller is responsible for the catch-error -> compress -> retry orchestration
    (Non-Goal here); this only performs the unconditional compression to Tretained.
    """
    cfg = _resolve_config(config, agent_name)
    return _compress(
        messages,
        cfg,
        trigger="context_overflow",
        session_id=session_id,
        user_id=user_id,
        agent_name=agent_name,
    )


def _summary_fingerprint(text: str) -> str:
    """Short stable hash of a summary body — enough to tell summaries apart without
    ever writing the (possibly sensitive) body to the append-only trace (AR16 D2)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _resolve_summary_model() -> str | None:
    """Resolve the summary route's model name for the trace (AR16 D4), defensively:
    observability must never break compression, so a resolution failure → None."""
    try:
        return str(_summary_route()[1].model)
    except Exception as exc:  # observability only — never propagate
        _logger.warn("compression_summary_model_resolve_failed", error=str(exc))
        return None


def _summary_route() -> tuple[ModelPolicySnapshot, ResolvedModelConfig]:
    from fleetent import agent_config

    policy = ModelPolicySnapshot.from_agent(agent_config.active_agent_or_default())
    cfg = policy.resolve("memory_extraction")[0]
    if cfg.protocol != "openai_chat" or not cfg.base_url or not cfg.model:
        raise ModelConfigError("memory_extraction route must target an openai_chat model")
    return policy, cfg


def _log_compression_safe(**kwargs: Any) -> None:
    """Write the compression trace, swallowing (but logging) any failure (AR16 D5)."""
    try:
        eval_logger.log_compression(**kwargs)
    except Exception as exc:  # observability must not become a failure point
        _logger.warn("compression_trace_failed", error=str(exc))


def _compress(
    messages: list[Any],
    cfg: ContextConfig,
    *,
    trigger: str = "tmax",
    session_id: str | None = None,
    user_id: str | None = None,
    agent_name: str | None = None,
) -> list[Any]:
    t0 = time.monotonic()
    tokens_before = estimate_tokens(messages)
    messages_before = len(messages)
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
        result = [m for m in messages if id(m) in head_ids or id(m) in tail_ids]
        _log_compression_safe(
            trigger=trigger,
            outcome="no_middle",
            tokens_before=tokens_before,
            tokens_after=estimate_tokens(result),
            messages_before=messages_before,
            messages_after=len(result),
            head_count=len(head),
            tail_count=len(tail),
            dropped_count=0,
            elapsed_s=time.monotonic() - t0,
            session_id=session_id,
            user_id=user_id,
            agent_name=agent_name,
        )
        return result

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
        _logger.warn("compression_summary_degraded", middle_count=len(new_middle))
        notice_msg: dict[str, str] = {"role": "system", "content": _MIDDLE_OMITTED_NOTICE}
        result = [*head, notice_msg, *tail]
        _log_compression_safe(
            trigger=trigger,
            outcome="degraded",
            tokens_before=tokens_before,
            tokens_after=estimate_tokens(result),
            messages_before=messages_before,
            messages_after=len(result),
            head_count=len(head),
            tail_count=len(tail),
            dropped_count=len(middle),
            elapsed_s=time.monotonic() - t0,
            session_id=session_id,
            user_id=user_id,
            agent_name=agent_name,
        )
        return result

    summary_msg: dict[str, str] = {
        "role": "system",
        "content": f"{_SUMMARY_PREFIX}\n{summary_text}",
    }
    result = [*head, summary_msg, *tail]
    _log_compression_safe(
        trigger=trigger,
        outcome="summarized",
        tokens_before=tokens_before,
        tokens_after=estimate_tokens(result),
        messages_before=messages_before,
        messages_after=len(result),
        head_count=len(head),
        tail_count=len(tail),
        dropped_count=len(middle),
        elapsed_s=time.monotonic() - t0,
        summary_model=_resolve_summary_model(),
        summary_fingerprint=_summary_fingerprint(summary_text),
        summary_len=len(summary_text),
        session_id=session_id,
        user_id=user_id,
        agent_name=agent_name,
    )
    return result


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
        policy, cfg = _summary_route()
        client = OpenAI(base_url=cfg.base_url, api_key=policy.require_api_key(cfg) or "fleetent")
        text = "\n".join(
            f"{_role(m)}: {_content(m)}"
            for m in messages
            if _role(m) in ("user", "assistant") and _content(m)
        )
        prompt = _build_summary_prompt(text, prev_summary)
        create_completion = cast(Any, client.chat.completions.create)
        response = create_completion(
            model=cfg.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            **cfg.params,
        )
        summary = response.choices[0].message.content
        if not summary:
            _logger.warn("compression_summary_empty_response")
            return None
        return cast(str, summary)
    except Exception as exc:
        _logger.warn("compression_summary_failed", error=str(exc))
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


# ── AR17: auto-compression anti-flap ─────────────────────────────────────────


@dataclass
class AntiFlapState:
    """Per-session anti-flap memory: recent auto-compression savings ratios, turns
    since the last auto compression, and whether auto compression is circuit-broken.

    Updated functionally (dataclasses.replace, never in place) so callers thread it
    explicitly; persisted per session_id in users.db, not in the message array.
    """

    recent_savings: tuple[float, ...] = ()
    turns_since_last_compress: int = 0
    auto_disabled: bool = False


def apply_anti_flap(
    messages: list[Any],
    state: AntiFlapState,
    config: ContextConfig | None = None,
    *,
    session_id: str | None = None,
    user_id: str | None = None,
    agent_name: str | None = None,
) -> tuple[list[Any], AntiFlapState]:
    """Auto-compression with anti-flap gating; returns (messages, updated state).

    Gates the AR12 auto path: a circuit breaker (consecutive low-savings) and a
    minimum-interval hysteresis window. Manual (`maybe_compress(force=True)`) and
    context-overflow entrypoints deliberately do NOT call this (D4 exemption).
    """
    cfg = _resolve_config(config, agent_name)
    flap_window = int(cfg.get("flap_window", _DEFAULT_FLAP_WINDOW))
    min_savings = float(cfg.get("min_savings_ratio", _DEFAULT_MIN_SAVINGS_RATIO))
    min_interval = int(cfg.get("min_interval_turns", _DEFAULT_MIN_INTERVAL_TURNS))

    trigger_line = int(cfg["max_tokens"] * cfg["tmax_ratio"])
    over_tmax = estimate_tokens(messages) > trigger_line
    advanced = state.turns_since_last_compress + 1

    # Circuit-broken or not over the line → no compression; just advance turns.
    if state.auto_disabled or not over_tmax:
        return messages, replace(state, turns_since_last_compress=advanced)

    # Minimum-interval hysteresis: too soon since the last auto compression.
    if advanced < min_interval:
        return messages, replace(state, turns_since_last_compress=advanced)

    before = estimate_tokens(messages)
    result = _compress(
        messages,
        cfg,
        trigger="tmax",
        session_id=session_id,
        user_id=user_id,
        agent_name=agent_name,
    )
    after = estimate_tokens(result)
    savings = (before - after) / before if before > 0 else 0.0
    window = (*state.recent_savings, savings)[-flap_window:]
    auto_disabled = len(window) == flap_window and all(s < min_savings for s in window)
    if auto_disabled and not state.auto_disabled:
        _logger.warn(
            "compression_auto_flap_disabled",
            recent_savings=window,
            min_savings_ratio=min_savings,
            flap_window=flap_window,
            session_id=session_id,
        )
    return result, AntiFlapState(
        recent_savings=window, turns_since_last_compress=0, auto_disabled=auto_disabled
    )


def _anti_flap_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_anti_flap_db() -> None:
    """Create the per-session anti-flap sister table, idempotently.

    A sister table keyed by session_id (not new columns on session-metadata-index's
    `sessions` table) keeps that change's schema/semantics untouched.
    """
    with _anti_flap_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_anti_flap (
              session_id        TEXT PRIMARY KEY,
              recent_savings    TEXT NOT NULL,
              turns_since       INTEGER NOT NULL,
              auto_disabled     INTEGER NOT NULL
            )
            """
        )


def load_anti_flap_state(session_id: str) -> AntiFlapState:
    """Load a session's AntiFlapState from users.db, or a fresh default if absent."""
    init_anti_flap_db()
    with _anti_flap_conn() as conn:
        row = conn.execute(
            "SELECT recent_savings, turns_since, auto_disabled "
            "FROM session_anti_flap WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if row is None:
        return AntiFlapState()
    return AntiFlapState(
        recent_savings=tuple(json.loads(row[0])),
        turns_since_last_compress=row[1],
        auto_disabled=bool(row[2]),
    )


def save_anti_flap_state(session_id: str, state: AntiFlapState) -> None:
    """Persist a session's AntiFlapState to users.db (insert or replace)."""
    init_anti_flap_db()
    with _anti_flap_conn() as conn:
        conn.execute(
            """
            INSERT INTO session_anti_flap (session_id, recent_savings, turns_since, auto_disabled)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
              recent_savings=excluded.recent_savings,
              turns_since=excluded.turns_since,
              auto_disabled=excluded.auto_disabled
            """,
            (
                session_id,
                json.dumps(list(state.recent_savings)),
                state.turns_since_last_compress,
                int(state.auto_disabled),
            ),
        )
