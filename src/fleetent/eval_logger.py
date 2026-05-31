"""Append-only JSONL trace logger for agent runs."""

import json
import time
from pathlib import Path
from typing import Any

from openai.types import CompletionUsage

_LOG_PATH = Path("data/traces.jsonl")
TRACE_PATH = Path("data/traces.jsonl")


def log_run(
    user_input: str,
    reply: str,
    messages: list[Any],
    elapsed_s: float,
    usage: CompletionUsage | None = None,
    model_used: str | None = None,
    user_id: str | None = None,
    agent_name: str | None = None,
    stop_reason: str | None = None,
    error_category: str | None = None,
) -> None:
    """Append one run record to the JSONL trace file."""
    entry: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input": user_input,
        "reply": reply,
        "messages": [_serialize(m) for m in messages],
        "elapsed_s": round(elapsed_s, 3),
        "tokens": (
            {
                "prompt": usage.prompt_tokens,
                "completion": usage.completion_tokens,
                "total": usage.total_tokens,
            }
            if usage
            else None
        ),
    }
    if model_used is not None:
        entry["model_used"] = model_used
    if user_id is not None:
        entry["user_id"] = user_id
    if agent_name is not None:
        entry["agent_name"] = agent_name
    if stop_reason is not None:
        entry["stop_reason"] = stop_reason
    if error_category is not None:
        entry["error_category"] = error_category
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def log(
    user_id: str,
    messages: list[Any],
    response: str,
    platform: str | None = None,
    session_id: str | None = None,
    channel_id: str | None = None,
    thread_id: str | None = None,
    message_id: str | None = None,
) -> None:
    """Append one IM-aware trace entry to the JSONL trace file."""
    entry: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user_id": user_id,
        "messages": [_serialize(m) for m in messages],
        "reply": response,
    }
    if platform is not None:
        entry["platform"] = platform
    if session_id is not None:
        entry["session_id"] = session_id
    if channel_id is not None:
        entry["channel_id"] = channel_id
    if thread_id is not None:
        entry["thread_id"] = thread_id
    if message_id is not None:
        entry["message_id"] = message_id
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRACE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _serialize(msg: Any) -> Any:
    if isinstance(msg, dict):
        return msg
    if hasattr(msg, "model_dump"):
        return msg.model_dump()
    return str(msg)
