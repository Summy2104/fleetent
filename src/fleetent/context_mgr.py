"""In-session context compression: summarize old history when token limit approaches."""

from typing import Any

from fleetent.model_router import get_client_and_config

ContextConfig = dict[str, Any]


def _default_config() -> ContextConfig:
    from fleetent.config import Settings

    s = Settings(anthropic_api_key="")
    return {
        "max_tokens": s.context_max_tokens,
        "compress_threshold": s.context_compress_threshold,
        "keep_recent": s.context_keep_recent,
    }


def estimate_tokens(messages: list[Any]) -> int:
    """Rough token count: 1 token ≈ 4 chars."""
    return sum(len(str(m)) for m in messages) // 4


def maybe_compress(
    messages: list[Any],
    config: ContextConfig | None = None,
) -> list[Any]:
    """If messages exceed threshold, compress and return new list. Otherwise return as-is."""
    cfg = config if config is not None else _default_config()
    threshold = int(cfg["max_tokens"] * cfg["compress_threshold"])
    if estimate_tokens(messages) <= threshold:
        return messages

    keep_recent = cfg["keep_recent"]

    # Separate system prompt from conversation
    system_msgs = [m for m in messages if _role(m) == "system"]
    conv_msgs = [m for m in messages if _role(m) != "system"]

    # Keep complete tool_call/tool_result pairs at tail to avoid LLM errors
    tail = _keep_tail(conv_msgs, keep_recent)
    to_summarize = conv_msgs[: len(conv_msgs) - len(tail)]

    summary_text = _summarize(to_summarize)
    summary_msg: dict[str, str] = {
        "role": "system",
        "content": f"[Earlier conversation summary]\n{summary_text}",
    }

    return [*system_msgs, summary_msg, *tail]


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
