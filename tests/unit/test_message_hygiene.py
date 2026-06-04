"""Unit tests for the pre-LLM message hygiene layer."""

from __future__ import annotations

import copy

import pytest

from fleetent.runtime.message_hygiene import (
    HygieneReport,
    MessageContractError,
    RepairKind,
    sanitize,
)

# ── RepairKind / HygieneReport ───────────────────────────────────────────────


def test_repair_kind_values_exist() -> None:
    assert RepairKind.merged_same_role
    assert RepairKind.inserted_placeholder
    assert RepairKind.filled_missing_tool_result
    assert RepairKind.removed_orphan_tool_result


def test_repair_kind_is_str_enum() -> None:
    assert isinstance(RepairKind.merged_same_role, str)
    assert RepairKind.merged_same_role == "merged_same_role"


def test_hygiene_report_defaults() -> None:
    report = HygieneReport()
    assert report.repairs == {}
    assert report.changed is False


def test_hygiene_report_changed_when_repairs_present() -> None:
    report = HygieneReport(repairs={RepairKind.removed_orphan_tool_result: 1})
    assert report.changed is True


# ── sanitize(): legal sequences ──────────────────────────────────────────────


def _assistant_tool_call(call_id: str, name: str = "f") -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}
        ],
    }


def test_sanitize_legal_sequence_unchanged() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    clean, report = sanitize(messages)
    assert report.changed is False
    assert report.repairs == {}
    assert clean == messages


def test_sanitize_returns_new_list_not_input() -> None:
    messages = [{"role": "user", "content": "hi"}]
    clean, _ = sanitize(messages)
    assert clean is not messages


def test_sanitize_does_not_mutate_input() -> None:
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "user", "content": "again"},
    ]
    before = copy.deepcopy(messages)
    sanitize(messages)
    assert messages == before


def test_sanitize_legal_tool_pairing_unchanged() -> None:
    messages = [
        {"role": "user", "content": "hi"},
        _assistant_tool_call("c1"),
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
        {"role": "assistant", "content": "done"},
    ]
    clean, report = sanitize(messages)
    assert report.changed is False
    assert clean == messages


# ── remove orphan tool_result ────────────────────────────────────────────────


def test_sanitize_removes_orphan_tool_result() -> None:
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "tool", "tool_call_id": "ghost", "content": "stale"},
        {"role": "assistant", "content": "ok"},
    ]
    clean, report = sanitize(messages)
    assert report.repairs.get(RepairKind.removed_orphan_tool_result) == 1
    assert all(m.get("role") != "tool" for m in clean)


def test_sanitize_keeps_tool_result_with_matching_call() -> None:
    messages = [
        _assistant_tool_call("c1"),
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    clean, report = sanitize(messages)
    assert RepairKind.removed_orphan_tool_result not in report.repairs
    assert any(m.get("role") == "tool" for m in clean)


def test_sanitize_counts_multiple_orphans() -> None:
    messages = [
        {"role": "tool", "tool_call_id": "g1", "content": "a"},
        {"role": "tool", "tool_call_id": "g2", "content": "b"},
        {"role": "user", "content": "hi"},
    ]
    _, report = sanitize(messages)
    assert report.repairs.get(RepairKind.removed_orphan_tool_result) == 2


# ── fill missing tool_result ─────────────────────────────────────────────────


def test_sanitize_fills_missing_tool_result() -> None:
    messages = [
        {"role": "user", "content": "hi"},
        _assistant_tool_call("c1"),
        {"role": "assistant", "content": "done"},
    ]
    clean, report = sanitize(messages)
    assert report.repairs.get(RepairKind.filled_missing_tool_result) == 1
    tool_msgs = [m for m in clean if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "c1"
    assert "工具执行失败" in tool_msgs[0]["content"]


def test_sanitize_filled_result_placed_after_assistant() -> None:
    messages = [
        _assistant_tool_call("c1"),
        {"role": "user", "content": "later"},
    ]
    clean, _ = sanitize(messages)
    # the tool result must immediately follow the assistant tool_call carrier
    idx_assistant = next(i for i, m in enumerate(clean) if m.get("role") == "assistant")
    assert clean[idx_assistant + 1]["role"] == "tool"
    assert clean[idx_assistant + 1]["tool_call_id"] == "c1"


def test_sanitize_fills_each_missing_call_in_multi_call_assistant() -> None:
    messages = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "a", "arguments": "{}"}},
                {"id": "c2", "type": "function", "function": {"name": "b", "arguments": "{}"}},
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    clean, report = sanitize(messages)
    assert report.repairs.get(RepairKind.filled_missing_tool_result) == 1
    ids = {m["tool_call_id"] for m in clean if m.get("role") == "tool"}
    assert ids == {"c1", "c2"}


# ── consecutive same-role ────────────────────────────────────────────────────


def test_sanitize_merges_adjacent_same_role_text() -> None:
    messages = [
        {"role": "user", "content": "part one"},
        {"role": "user", "content": "part two"},
    ]
    clean, report = sanitize(messages)
    assert report.repairs.get(RepairKind.merged_same_role) == 1
    user_msgs = [m for m in clean if m.get("role") == "user"]
    assert len(user_msgs) == 1
    assert "part one" in user_msgs[0]["content"]
    assert "part two" in user_msgs[0]["content"]


def test_sanitize_no_adjacent_same_role_after_repair() -> None:
    messages = [
        {"role": "assistant", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "assistant", "content": "c"},
    ]
    clean, _ = sanitize(messages)
    roles = [m["role"] for m in clean]
    assert all(roles[i] != roles[i + 1] for i in range(len(roles) - 1))


def test_sanitize_inserts_placeholder_before_tool_call_carrier() -> None:
    # An assistant text message immediately followed by an assistant tool_call
    # carrier is same-role but cannot be text-merged (merging would corrupt the
    # carrier). A placeholder of the opposite role must separate them.
    messages = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": "thinking..."},
        _assistant_tool_call("c1"),
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    clean, report = sanitize(messages)
    roles = [m["role"] for m in clean]
    assert all(roles[i] != roles[i + 1] for i in range(len(roles) - 1))
    assert report.repairs.get(RepairKind.inserted_placeholder, 0) >= 1


# ── unrepairable → MessageContractError ──────────────────────────────────────


def test_sanitize_raises_on_message_missing_role() -> None:
    messages = [{"content": "no role here"}]
    with pytest.raises(MessageContractError):
        sanitize(messages)


def test_sanitize_raises_on_tool_message_missing_call_id() -> None:
    messages = [
        _assistant_tool_call("c1"),
        {"role": "tool", "content": "no id"},
    ]
    with pytest.raises(MessageContractError):
        sanitize(messages)


def test_message_contract_error_carries_description() -> None:
    messages = [{"content": "broken"}]
    with pytest.raises(MessageContractError) as exc_info:
        sanitize(messages)
    assert str(exc_info.value)


# ── idempotency ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "messages",
    [
        [
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
        ],
        [
            {"role": "user", "content": "hi"},
            _assistant_tool_call("c1"),
            {"role": "assistant", "content": "done"},
        ],
        [
            {"role": "tool", "tool_call_id": "ghost", "content": "x"},
            {"role": "user", "content": "hi"},
        ],
        [_assistant_tool_call("c1"), _assistant_tool_call("c2")],
    ],
)
def test_sanitize_is_idempotent(messages: list[dict]) -> None:
    once, _ = sanitize(messages)
    twice, report = sanitize(once)
    assert report.changed is False
    assert twice == once
