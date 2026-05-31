"""Append-only JSONL trace logger for agent runs."""

import base64
import json
import re
import time
from pathlib import Path
from typing import Any

from openai.types import CompletionUsage

_LOG_PATH = Path("data/traces.jsonl")
TRACE_PATH = Path("data/traces.jsonl")

# Matches a base64 data URL so an image block can be summarized as
# "[图片：{mime}，{bytes}字节]" instead of writing the full base64 string.
_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<b64>.*)$", re.DOTALL)


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
    hygiene_repairs: dict[str, int] | None = None,
    cache_tokens: dict[str, int] | None = None,
    disabled_skills_trace: list[dict[str, str]] | None = None,
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
    if hygiene_repairs is not None:
        entry["hygiene_repairs"] = hygiene_repairs
    if cache_tokens is not None:
        entry["cache_tokens"] = cache_tokens
    if disabled_skills_trace:
        entry["disabled_skills_trace"] = disabled_skills_trace
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
        return _placeholder_images(msg)
    if hasattr(msg, "model_dump"):
        return _placeholder_images(msg.model_dump())
    return str(msg)


def _placeholder_images(msg: dict[str, Any]) -> dict[str, Any]:
    """Replace image_url blocks with a compact placeholder; never write base64."""
    content = msg.get("content")
    if not isinstance(content, list):
        return msg
    new_content = [
        _placeholder_block(block) if isinstance(block, dict) else block for block in content
    ]
    return {**msg, "content": new_content}


def _placeholder_block(block: dict[str, Any]) -> dict[str, Any]:
    if block.get("type") != "image_url":
        return block
    url = (block.get("image_url") or {}).get("url", "")
    match = _DATA_URL_RE.match(url) if isinstance(url, str) else None
    if not match:
        return {"type": "text", "text": "[图片]"}
    mime = match.group("mime")
    n_bytes = len(base64.b64decode(match.group("b64"), validate=False))
    return {"type": "text", "text": f"[图片：{mime}，{n_bytes}字节]"}
