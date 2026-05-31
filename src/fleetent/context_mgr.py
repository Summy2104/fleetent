"""In-session context compression: summarize old history when token limit approaches."""

from typing import Any

from fleetent.model_router import get_client_and_config

ContextConfig = dict[str, Any]

# Fixed token estimate per image block (AR21). A real backend bills an image by
# its pixel dimensions (Anthropic caps around ~1600 tokens); 1000 is a
# conservative constant that avoids charging the multi-thousand-char base64
# string, which would falsely trip the compression threshold.
_IMAGE_BLOCK_TOKENS = 1000

# Conservative allowance for the injected summary system message when projecting
# whether a candidate tail fits under the Tretained target line. The summary body
# is bounded by `_summarize`'s max_tokens=512.
_SUMMARY_OVERHEAD_TOKENS = 512


def _default_config() -> ContextConfig:
    from fleetent.config import Settings

    s = Settings()
    return {
        "max_tokens": s.context_max_tokens,
        "tmax_ratio": s.context_tmax_ratio,
        "tretained_ratio": s.context_tretained_ratio,
        "keep_recent": s.context_keep_recent,
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

    # Keep the cacheable system head out of compression (prompt-cache relies on it).
    system_msgs = [m for m in messages if _role(m) == "system"]
    conv_msgs = [m for m in messages if _role(m) != "system"]

    tail = _select_tail(conv_msgs, keep_recent, target, system_msgs)
    to_summarize = conv_msgs[: len(conv_msgs) - len(tail)]

    summary_text = _summarize(to_summarize)
    summary_msg: dict[str, str] = {
        "role": "system",
        "content": f"[Earlier conversation summary]\n{summary_text}",
    }

    return [*system_msgs, summary_msg, *tail]


def _select_tail(
    conv_msgs: list[Any],
    keep_recent: int,
    target: int,
    system_msgs: list[Any],
) -> list[Any]:
    """Pick the largest tail (down to a 1-message floor) whose estimate fits target.

    Starts from `keep_recent` and shrinks while the projected total (system head +
    summary placeholder + tail) exceeds the Tretained target line. `_keep_tail`
    keeps tool_call/tool_result pairs whole, so the realized estimate MAY end up
    slightly above target — that upper-bound relaxation is accepted (D3).
    """
    n = min(keep_recent, len(conv_msgs)) if conv_msgs else 0
    fixed = estimate_tokens(system_msgs) + _SUMMARY_OVERHEAD_TOKENS
    while n > 1:
        tail = _keep_tail(conv_msgs, n)
        if fixed + estimate_tokens(tail) <= target:
            return tail
        n -= 1
    return _keep_tail(conv_msgs, max(n, 1)) if conv_msgs else []


def _summarize(messages: list[Any]) -> str:
    try:
        client, cfg = get_client_and_config("memory_extraction")
        text = "\n".join(
            f"{_role(m)}: {_content(m)}"
            for m in messages
            if _role(m) in ("user", "assistant") and _content(m)
        )
        response = client.chat.completions.create(
            model=cfg.model,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Summarize this conversation concisely. "
                        "Focus on user goals and completed actions:\n\n" + text
                    ),
                }
            ],
            max_tokens=512,
        )
        return response.choices[0].message.content or ""
    except Exception:
        return "[Earlier conversation summary unavailable]"


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
