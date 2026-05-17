"""Append-only JSONL trace logger for agent runs."""

import json
import time
from pathlib import Path
from typing import Any

from openai.types import CompletionUsage

_LOG_PATH = Path("data/traces.jsonl")


def log_run(
    user_input: str,
    reply: str,
    messages: list[Any],
    elapsed_s: float,
    usage: CompletionUsage | None = None,
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
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _serialize(msg: Any) -> Any:
    if isinstance(msg, dict):
        return msg
    if hasattr(msg, "model_dump"):
        return msg.model_dump()
    return str(msg)
