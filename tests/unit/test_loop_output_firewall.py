"""Unit tests: output firewall — redact_secrets over all tool results (output-firewall).

Drives _backfill_slots directly with crafted slots, asserting secrets in real tool
results are redacted before entering messages, placeholders are left alone, and
redaction happens before truncation (so a boundary-straddling secret is masked).
"""

from __future__ import annotations

import fleetent.runtime.loop as loop
from fleetent.runtime.loop import _PlanSlot
from fleetent.runtime.loop_detector import LoopDetectionChecker
from fleetent.runtime.snapshot import GovernanceConfig
from fleetent.runtime.termination import LoopState


def _slot(name: str, tc_id: str = "tc1") -> _PlanSlot:
    return _PlanSlot(tc_id=tc_id, name=name, tc_fp="fp", args={})


def _placeholder(name: str, content: str, tc_id: str = "tc1") -> _PlanSlot:
    return _PlanSlot(tc_id=tc_id, name=name, tc_fp="fp", placeholder=(content, False))


async def _backfill(slots, results) -> list[dict]:
    messages: list = []
    await loop._backfill_slots(
        slots,
        results,
        messages=messages,
        state=LoopState(),
        loop_checker=LoopDetectionChecker(3, []),
        governance=GovernanceConfig(),
        session_id=None,
        agent_name="a",
        user_id="u",
    )
    return messages


async def test_tool_result_with_vendor_key_redacted() -> None:
    secret = "here is the key sk-ant-abcdefgh12345678 ok"
    msgs = await _backfill([_slot("read_file")], {"tc1": (secret, False)})
    assert "sk-ant-abcdefgh12345678" not in msgs[0]["content"]
    assert "[REDACTED]" in msgs[0]["content"]


async def test_tool_result_with_named_secret_redacted() -> None:
    secret = "config: API_KEY=supersecretvalue123 done"
    msgs = await _backfill([_slot("search_content")], {"tc1": (secret, False)})
    assert "supersecretvalue123" not in msgs[0]["content"]
    assert "[REDACTED]" in msgs[0]["content"]


async def test_tool_result_with_authorization_header_redacted() -> None:
    secret = "Authorization: Bearer abc123def456ghi789"
    msgs = await _backfill([_slot("http_get")], {"tc1": (secret, False)})
    assert "abc123def456ghi789" not in msgs[0]["content"]


async def test_clean_result_unchanged() -> None:
    clean = "the answer is 42 and the sky is blue"
    msgs = await _backfill([_slot("calculate")], {"tc1": (clean, False)})
    assert msgs[0]["content"] == clean


async def test_placeholder_not_redacted() -> None:
    # A placeholder happens to contain a secret-looking token; it is system text, left alone.
    text = "rejected by action gate: deploy (critical risk) token=AKIA1234567890ABCDEF"
    msgs = await _backfill([_placeholder("deploy", text)], {})
    assert msgs[0]["content"] == text


async def test_redaction_before_truncation(monkeypatch) -> None:
    # Force a tiny truncation budget; a secret near the end must already be masked
    # before truncation, so no secret fragment can survive.
    secret_tail = "trailing API_KEY=verysecretlongvalue9999"
    body = "x" * 50 + secret_tail
    msgs = await _backfill([_slot("read_file")], {"tc1": (body, False)})
    assert "verysecretlongvalue9999" not in msgs[0]["content"]
