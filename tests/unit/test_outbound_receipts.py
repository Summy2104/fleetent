"""Unit: outbound delivery receipts (§1, D1).

send_to / send_file_to return a structured DeliveryReceipt (ok + target + kind + provider
ref), extracting the Slack ts / file_id on success and the error on failure — keeping the
never-throw semantics (a connector exception becomes a failed receipt, not a raise).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fleetent import outbound
from fleetent.outbound import DeliveryReceipt


def _slack_ok() -> MagicMock:
    c = MagicMock()
    c.conversations_open = AsyncMock(return_value={"channel": {"id": "D1"}})
    c.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1700.5", "channel": "D1"})
    c.files_upload_v2 = AsyncMock(return_value={"ok": True, "files": [{"id": "F123"}]})
    return c


def _slack_boom() -> MagicMock:
    c = MagicMock()
    c.conversations_open = AsyncMock(side_effect=RuntimeError("network down"))
    return c


def test_receipt_is_structured():
    r = DeliveryReceipt(ok=True, platform="slack", target="U1", target_type="user", kind="text")
    assert r.ok and r.kind == "text" and r.provider_ref is None and r.error is None


async def test_send_to_dm_success_extracts_ts():
    r = await outbound.send_to("slack", _slack_ok(), "U1", "hi")
    assert isinstance(r, DeliveryReceipt)
    assert r.ok and r.kind == "text" and r.target == "U1" and r.target_type == "user"
    assert r.provider_ref == "1700.5"
    assert r.error is None


async def test_send_file_success_extracts_file_id():
    r = await outbound.send_file_to("slack", _slack_ok(), "U1", "/tmp/x.csv")
    assert r.ok and r.kind == "file"
    assert r.provider_ref == "F123"


async def test_send_to_failure_is_failed_receipt_not_raise():
    r = await outbound.send_to("slack", _slack_boom(), "U1", "hi")
    assert r.ok is False
    assert r.provider_ref is None
    assert r.error  # non-empty reason


async def test_send_file_failure_is_failed_receipt():
    r = await outbound.send_file_to("slack", _slack_boom(), "U1", "/tmp/x.csv")
    assert r.ok is False and r.kind == "file" and r.error


async def test_unsupported_platform_is_failed_receipt():
    r = await outbound.send_to("discord", MagicMock(), "U1", "hi")
    assert r.ok is False and r.error
