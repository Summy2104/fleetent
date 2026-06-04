"""Pre-LLM message hygiene layer.

OpenAI-compatible backends reject message sequences that violate the chat
contract (adjacent same-role messages, a `tool_call` without its matching
`tool_result`, or an orphan `tool_result`). Such sequences arise from context
compression, approval placeholders, normalized tool crashes, and session
round-trips. `sanitize()` validates and repairs a sequence just before it is
sent to the model, returning a guaranteed-legal new list plus a report of the
repairs performed. It is a pure function: the input list is never mutated.

This mirrors the termination framework (AR1) and error classifier (AR5): a
small set of fixed, ordered rules, no global mutable state, and a report the
caller writes to the trace. Violations that no rule can safely fix raise
`MessageContractError` so the loop fails locally rather than triggering a remote
400 whose stack is far from the cause.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Placeholder content for a tool_call that never produced a result. Chinese and
# explicitly labelled "auto-filled" so the model does not misread it as a real
# tool output.
_MISSING_TOOL_RESULT_TEXT = "工具执行失败（缺失结果，已自动补全）"

# Placeholder inserted to separate two adjacent same-role messages that cannot be
# text-merged (e.g. two tool_call carriers).
_PLACEHOLDER_SEPARATOR_TEXT = "（占位消息，自动插入以保持消息序列合法）"

# Roles whose adjacent same-role text bodies may be merged. tool messages are
# never merged (they are keyed by tool_call_id); system is left untouched.
_MERGEABLE_ROLES = frozenset({"user", "assistant"})


class RepairKind(StrEnum):
    """Categories of repair the hygiene layer performs. str-valued for JSONL."""

    merged_same_role = "merged_same_role"
    inserted_placeholder = "inserted_placeholder"
    filled_missing_tool_result = "filled_missing_tool_result"
    removed_orphan_tool_result = "removed_orphan_tool_result"


@dataclass
class HygieneReport:
    """Summary of repairs applied to one message sequence."""

    repairs: dict[RepairKind, int] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.repairs)

    def _bump(self, kind: RepairKind, n: int = 1) -> None:
        if n:
            self.repairs[kind] = self.repairs.get(kind, 0) + n


class MessageContractError(Exception):
    """A message-sequence violation no hygiene rule can safely repair.

    Raised before any LLM call so the failure is diagnosed locally rather than
    surfacing as a remote 400. Carries a human-readable description of the
    violation; not swallowed by the loop (logged + handled at the loop exit).
    """


def sanitize(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], HygieneReport]:
    """Validate and repair a message sequence; return (clean_copy, report).

    Never mutates the input. Repairs run in a fixed order (design D2): remove
    orphan tool_results → fill missing tool_results → fix consecutive same-role
    messages. Structural damage that cannot be safely repaired raises
    `MessageContractError`.
    """
    _validate_structure(messages)

    report = HygieneReport()
    work = copy.deepcopy(messages)

    work = _remove_orphan_tool_results(work, report)
    work = _fill_missing_tool_results(work, report)
    work = _fix_consecutive_same_role(work, report)

    return work, report


def _validate_structure(messages: list[dict[str, Any]]) -> None:
    """Raise MessageContractError on damage no rule can fix (design D3)."""
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            raise MessageContractError(f"message at index {i} is not a dict: {msg!r}")
        role = msg.get("role")
        if not role:
            raise MessageContractError(f"message at index {i} is missing a role: {msg!r}")
        if role == "tool" and not msg.get("tool_call_id"):
            raise MessageContractError(
                f"tool message at index {i} is missing tool_call_id and cannot be "
                f"attributed to a tool_call: {msg!r}"
            )


def _tool_call_ids(msg: dict[str, Any]) -> list[str]:
    """tool_call ids carried by an assistant message (empty for other roles)."""
    ids: list[str] = []
    for tc in msg.get("tool_calls") or []:
        tc_id = tc.get("id") if isinstance(tc, dict) else None
        if tc_id:
            ids.append(tc_id)
    return ids


def _remove_orphan_tool_results(
    messages: list[dict[str, Any]], report: HygieneReport
) -> list[dict[str, Any]]:
    """Drop tool messages whose tool_call_id was not announced by a prior call."""
    known_ids: set[str] = set()
    result: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "assistant":
            known_ids.update(_tool_call_ids(msg))
        if msg.get("role") == "tool" and msg.get("tool_call_id") not in known_ids:
            report._bump(RepairKind.removed_orphan_tool_result)
            continue
        result.append(msg)
    return result


def _fill_missing_tool_results(
    messages: list[dict[str, Any]], report: HygieneReport
) -> list[dict[str, Any]]:
    """Insert a placeholder tool_result for any tool_call lacking one downstream."""
    satisfied_ids = {
        m["tool_call_id"] for m in messages if m.get("role") == "tool" and m.get("tool_call_id")
    }
    result: list[dict[str, Any]] = []
    for msg in messages:
        result.append(msg)
        if msg.get("role") != "assistant":
            continue
        for call_id in _tool_call_ids(msg):
            if call_id not in satisfied_ids:
                result.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": _MISSING_TOOL_RESULT_TEXT,
                    }
                )
                satisfied_ids.add(call_id)
                report._bump(RepairKind.filled_missing_tool_result)
    return result


def _is_tool_call_carrier(msg: dict[str, Any]) -> bool:
    return bool(msg.get("tool_calls"))


def _merge_text(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Concatenate two same-role text messages into one (b appended to a)."""
    merged = copy.deepcopy(a)
    parts = [c for c in (a.get("content"), b.get("content")) if c]
    merged["content"] = "\n".join(str(p) for p in parts)
    return merged


def _fix_consecutive_same_role(
    messages: list[dict[str, Any]], report: HygieneReport
) -> list[dict[str, Any]]:
    """Collapse adjacent same-role messages: merge text, else insert a separator.

    Only user/assistant roles participate; tool messages are paired by id and
    never adjacent-merged. A tool_call carrier cannot be text-merged, so two
    adjacent same-role messages where either side carries tool_calls are kept
    apart with a placeholder of the opposite role.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        if not result:
            result.append(msg)
            continue
        prev = result[-1]
        same_role = prev.get("role") == msg.get("role")
        if same_role and msg.get("role") in _MERGEABLE_ROLES:
            if _is_tool_call_carrier(prev) or _is_tool_call_carrier(msg):
                result.append(_separator_for(msg["role"]))
                report._bump(RepairKind.inserted_placeholder)
                result.append(msg)
            else:
                result[-1] = _merge_text(prev, msg)
                report._bump(RepairKind.merged_same_role)
            continue
        result.append(msg)
    return result


def _separator_for(adjacent_role: str) -> dict[str, Any]:
    """A placeholder message of the role opposite `adjacent_role`."""
    role = "user" if adjacent_role == "assistant" else "assistant"
    return {"role": role, "content": _PLACEHOLDER_SEPARATOR_TEXT}
