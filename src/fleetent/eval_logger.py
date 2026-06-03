"""Append-only JSONL trace logger for agent runs."""

import base64
import json
import re
import time
from pathlib import Path
from typing import Any

from openai.types import CompletionUsage

from fleetent.integrations.sandbox import secrets as sandbox_secrets

# Single trace path constant for all three writers (log_run / log /
# log_sandbox_exec). One injectable module-level path means tests monkeypatch
# exactly one attribute to isolate every write (no leaked second alias).
TRACE_PATH = Path("data/traces.jsonl")

# Placeholder written in place of a sensitive-named tool_call argument value.
REDACTED_PLACEHOLDER = "[REDACTED]"

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
    budget_dimension: str | None = None,
    budget_scope: str | None = None,
) -> None:
    """Append one run record to the JSONL trace file."""
    entry: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": "agent_run",
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
    if budget_dimension is not None:
        entry["budget_dimension"] = budget_dimension
    if budget_scope is not None:
        entry["budget_scope"] = budget_scope
    if error_category is not None:
        entry["error_category"] = error_category
    if hygiene_repairs is not None:
        entry["hygiene_repairs"] = hygiene_repairs
    if cache_tokens is not None:
        entry["cache_tokens"] = cache_tokens
    if disabled_skills_trace:
        entry["disabled_skills_trace"] = disabled_skills_trace
    if _has_redacted_tool_calls(messages):
        entry["secrets_redacted"] = True
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRACE_PATH.open("a", encoding="utf-8") as f:
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
        "kind": "im_message",
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
    if _has_redacted_tool_calls(messages):
        entry["secrets_redacted"] = True
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRACE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def log_sandbox_exec(
    elapsed_s: float,
    exit_code: int,
    stdout_bytes: int,
    stderr_bytes: int,
    sandbox_scope: str | None = None,
    agent_name: str | None = None,
    user_id: str | None = None,
) -> None:
    """Append one sandbox-execution trace entry to the JSONL trace file.

    Records only metadata (sizes, timing, exit code) — never the code source or
    raw stdout/stderr content — consistent with the module's "no raw payloads"
    principle and to avoid log bloat / sensitive data on disk.
    """
    entry: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": "sandbox_exec",
        "elapsed_s": round(elapsed_s, 3),
        "exit_code": exit_code,
        "stdout_bytes": stdout_bytes,
        "stderr_bytes": stderr_bytes,
    }
    if sandbox_scope is not None:
        entry["sandbox_scope"] = sandbox_scope
    if agent_name is not None:
        entry["agent_name"] = agent_name
    if user_id is not None:
        entry["user_id"] = user_id
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRACE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def log_compression(
    trigger: str,
    outcome: str,
    tokens_before: int,
    tokens_after: int,
    messages_before: int,
    messages_after: int,
    head_count: int,
    tail_count: int,
    dropped_count: int,
    elapsed_s: float,
    summary_model: str | None = None,
    summary_fingerprint: str | None = None,
    summary_len: int | None = None,
    user_id: str | None = None,
    agent_name: str | None = None,
    session_id: str | None = None,
) -> None:
    """Append one context-compression trace entry (AR16).

    Records only metadata and a summary fingerprint — never raw messages or the
    summary body — consistent with the module's "no raw payloads" principle. A
    `kind: "compression"` makes every compression event independently queryable
    (one run may compress multiple times).
    """
    entry: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": "compression",
        "trigger": trigger,
        "outcome": outcome,
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "messages_before": messages_before,
        "messages_after": messages_after,
        "head_count": head_count,
        "tail_count": tail_count,
        "dropped_count": dropped_count,
        "elapsed_s": round(elapsed_s, 3),
    }
    if summary_model is not None:
        entry["summary_model"] = summary_model
    if summary_fingerprint is not None:
        entry["summary_fingerprint"] = summary_fingerprint
    if summary_len is not None:
        entry["summary_len"] = summary_len
    if user_id is not None:
        entry["user_id"] = user_id
    if agent_name is not None:
        entry["agent_name"] = agent_name
    if session_id is not None:
        entry["session_id"] = session_id
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRACE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _has_redacted_tool_calls(messages: list[Any]) -> bool:
    """Whether any message carries a sensitive-named tool_call arg that gets redacted
    in the trace (T3). Used to set an audit-only `secrets_redacted` marker on the
    entry — surfaces "a secret was present" without writing the value itself."""
    return any(_msg_has_sensitive_tool_arg(m) for m in messages)


def _msg_has_sensitive_tool_arg(msg: Any) -> bool:
    m = msg if isinstance(msg, dict) else (msg.model_dump() if hasattr(msg, "model_dump") else None)
    if not isinstance(m, dict) or not isinstance(m.get("tool_calls"), list):
        return False
    for tc in m["tool_calls"]:
        fn = tc.get("function") if isinstance(tc, dict) else None
        raw = fn.get("arguments") if isinstance(fn, dict) else None
        if not isinstance(raw, str):
            continue
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict) and any(sandbox_secrets.is_sensitive_name(k) for k in parsed):
            return True
    return False


def _serialize(msg: Any) -> Any:
    if isinstance(msg, dict):
        return _redact_tool_calls(_placeholder_images(msg))
    if hasattr(msg, "model_dump"):
        return _redact_tool_calls(_placeholder_images(msg.model_dump()))
    return str(msg)


def _redact_tool_calls(msg: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive-named tool_call argument values before they hit trace.

    The real leak vector is the assistant message's ``tool_calls[].function.
    arguments`` (LLM-produced JSON) landing in the append-only trace. Reusing
    the SB5 single source of truth (``sandbox_secrets.is_sensitive_name``), any
    top-level argument whose NAME is sensitive has its value replaced. Same
    layer/idiom as ``_placeholder_images``: produces a new representation, never
    mutating the runtime object; only the to-be-persisted trace shape changes.
    Name-only — values are never scanned (known SB5 limitation).
    """
    tool_calls = msg.get("tool_calls")
    if not isinstance(tool_calls, list):
        return msg
    return {**msg, "tool_calls": [_redact_tool_call(tc) for tc in tool_calls]}


def _redact_tool_call(tc: Any) -> Any:
    if not isinstance(tc, dict):
        return tc
    fn = tc.get("function")
    if not isinstance(fn, dict):
        return tc
    raw_args = fn.get("arguments")
    if not isinstance(raw_args, str):
        return tc
    try:
        parsed = json.loads(raw_args)
    except (json.JSONDecodeError, ValueError):
        return tc  # Malformed JSON: degrade to existing behavior, never raise.
    if not isinstance(parsed, dict):
        return tc
    redacted = {
        k: (REDACTED_PLACEHOLDER if sandbox_secrets.is_sensitive_name(k) else v)
        for k, v in parsed.items()
    }
    return {**tc, "function": {**fn, "arguments": json.dumps(redacted, ensure_ascii=False)}}


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
