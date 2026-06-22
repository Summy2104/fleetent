"""Unit: delivery fact-trailer rendering (§3.1, D4).

Deterministic one-line trailer from the run's delivery ledger: file/message success
counts with masked target summaries + a failure list. Empty ledger → no trailer (None).
"""

from __future__ import annotations

from fleetent.observability.traces import render_delivery_trailer
from fleetent.outbound import DeliveryReceipt


def _r(kind, ok, target="U0123456789", error=None):
    return DeliveryReceipt(
        ok=ok, platform="slack", target=target, target_type="user", kind=kind, error=error
    )


def test_empty_ledger_no_trailer():
    assert render_delivery_trailer([]) is None
    assert render_delivery_trailer(None) is None


def test_all_success_file_and_message():
    out = render_delivery_trailer([_r("file", True), _r("text", True)])
    assert out is not None
    assert out.startswith("📬")
    assert "文件 1" in out and "消息 1" in out
    assert "失败" not in out


def test_mixed_success_file_and_failed_message():
    out = render_delivery_trailer([_r("file", True), _r("text", False, error="network down")])
    assert "文件 1" in out
    assert "失败 1" in out and "network down" in out


def test_target_is_masked():
    out = render_delivery_trailer([_r("file", True, target="U0123456789")])
    assert "U0123456789" not in out  # full id never shown
    assert "U01" in out  # masked head retained


def test_only_failures():
    out = render_delivery_trailer([_r("file", False, error="boom")])
    assert "失败 1" in out and "boom" in out
    assert "文件 1（" not in out  # no success file group


# ── _append_delivery_trailer emit switch (cron fired-runs suppress the trailer) ──


def _ctx_with_receipt():
    from types import SimpleNamespace

    return SimpleNamespace(delivery_ledger=[_r("text", True)])


def test_append_trailer_emit_true_appends():
    from fleetent.runtime import loop

    out = loop._append_delivery_trailer("body", _ctx_with_receipt(), emit=True)
    assert out.startswith("body") and "📬" in out


def test_append_trailer_emit_false_returns_reply_unchanged():
    from fleetent.runtime import loop

    out = loop._append_delivery_trailer("body", _ctx_with_receipt(), emit=False)
    assert out == "body"  # fired-run: no operator-facing trailer


def test_append_trailer_default_emit_is_true():
    from fleetent.runtime import loop

    out = loop._append_delivery_trailer("[SILENT]", _ctx_with_receipt())
    assert "📬" in out  # default keeps interactive behavior
