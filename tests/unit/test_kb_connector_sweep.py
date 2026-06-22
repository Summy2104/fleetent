"""Unit tests: KB connector sweep — expiry detection and sweep behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, call, patch


# ── Task 3.1: expiry detection (pure function) ──────────────────────────────


def _row(
    *,
    enabled: bool = True,
    interval: int | None = 3600,
    last: str | None = None,
) -> dict:
    return {
        "connector_id": "c1",
        "enabled": enabled,
        "sync_interval_seconds": interval,
        "last_scheduled_sync_at": last,
        "kind": "google_drive",
        "tenant_id": "t1",
        "kb_id": "kb1",
        "config": {},
        "custom": {},
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }


def _now_str() -> str:
    return datetime.now(UTC).isoformat()


def _ago(seconds: int) -> str:
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat()


def test_due_when_last_is_none():
    from fleetent.platform.knowledge_base_management.kb_connector_sweep import is_connector_due

    assert is_connector_due(_row(last=None), datetime.now(UTC)) is True


def test_due_when_elapsed_exceeds_interval():
    from fleetent.platform.knowledge_base_management.kb_connector_sweep import is_connector_due

    row = _row(interval=3600, last=_ago(3601))
    assert is_connector_due(row, datetime.now(UTC)) is True


def test_not_due_when_elapsed_less_than_interval():
    from fleetent.platform.knowledge_base_management.kb_connector_sweep import is_connector_due

    row = _row(interval=3600, last=_ago(100))
    assert is_connector_due(row, datetime.now(UTC)) is False


def test_not_due_when_disabled():
    from fleetent.platform.knowledge_base_management.kb_connector_sweep import is_connector_due

    row = _row(enabled=False, interval=3600, last=None)
    assert is_connector_due(row, datetime.now(UTC)) is False


def test_not_due_when_interval_is_none():
    from fleetent.platform.knowledge_base_management.kb_connector_sweep import is_connector_due

    row = _row(interval=None, last=None)
    assert is_connector_due(row, datetime.now(UTC)) is False


def test_due_exactly_at_interval_boundary():
    from fleetent.platform.knowledge_base_management.kb_connector_sweep import is_connector_due

    row = _row(interval=3600, last=_ago(3600))
    assert is_connector_due(row, datetime.now(UTC)) is True


# ── Task 3.2: sweep behaviour ───────────────────────────────────────────────


def test_sweep_enqueues_due_connector():
    from fleetent.platform.knowledge_base_management import kb_connector_sweep as sweep_mod

    due_row = _row()
    due_row["connector_id"] = "due-1"
    due_row["last_scheduled_sync_at"] = _ago(7200)

    with (
        patch.object(sweep_mod, "list_schedulable_connectors", return_value=[due_row]),
        patch.object(sweep_mod, "enqueue_connector_job") as mock_enq,
        patch.object(sweep_mod, "update_last_scheduled_sync_at") as mock_upd,
    ):
        sweep_mod.sweep()

    mock_enq.assert_called_once_with(due_row)
    mock_upd.assert_called_once()
    assert mock_upd.call_args[0][0] == "due-1"


def test_sweep_skips_not_due_connector():
    from fleetent.platform.knowledge_base_management import kb_connector_sweep as sweep_mod

    fresh_row = _row()
    fresh_row["connector_id"] = "fresh-1"
    fresh_row["last_scheduled_sync_at"] = _ago(10)

    with (
        patch.object(sweep_mod, "list_schedulable_connectors", return_value=[fresh_row]),
        patch.object(sweep_mod, "enqueue_connector_job") as mock_enq,
        patch.object(sweep_mod, "update_last_scheduled_sync_at") as mock_upd,
    ):
        sweep_mod.sweep()

    mock_enq.assert_not_called()
    mock_upd.assert_not_called()


def test_sweep_advances_last_scheduled_sync_at_after_enqueue():
    from fleetent.platform.knowledge_base_management import kb_connector_sweep as sweep_mod

    due_row = _row()
    due_row["connector_id"] = "adv-1"
    due_row["last_scheduled_sync_at"] = None

    captured_ts: list[str] = []

    def capture_update(connector_id: str, ts: str) -> None:
        captured_ts.append(ts)

    with (
        patch.object(sweep_mod, "list_schedulable_connectors", return_value=[due_row]),
        patch.object(sweep_mod, "enqueue_connector_job"),
        patch.object(sweep_mod, "update_last_scheduled_sync_at", side_effect=capture_update),
    ):
        sweep_mod.sweep()

    assert len(captured_ts) == 1
    # Timestamp must be a recent ISO string (within the last 5 seconds)
    ts_dt = datetime.fromisoformat(captured_ts[0])
    assert abs((datetime.now(UTC) - ts_dt).total_seconds()) < 5


def test_sweep_continues_after_enqueue_error():
    from fleetent.platform.knowledge_base_management import kb_connector_sweep as sweep_mod

    rows = [
        {**_row(), "connector_id": "err-1", "last_scheduled_sync_at": _ago(7200)},
        {**_row(), "connector_id": "ok-1", "last_scheduled_sync_at": _ago(7200)},
    ]

    with (
        patch.object(sweep_mod, "list_schedulable_connectors", return_value=rows),
        patch.object(
            sweep_mod, "enqueue_connector_job", side_effect=[RuntimeError("queue full"), None]
        ),
        patch.object(sweep_mod, "update_last_scheduled_sync_at") as mock_upd,
    ):
        sweep_mod.sweep()  # must not raise

    # ok-1 should still be updated despite err-1 failing
    updated_ids = [c.args[0] for c in mock_upd.call_args_list]
    assert "ok-1" in updated_ids
    assert "err-1" not in updated_ids


def test_sweep_does_not_raise_on_empty_list():
    from fleetent.platform.knowledge_base_management import kb_connector_sweep as sweep_mod

    with patch.object(sweep_mod, "list_schedulable_connectors", return_value=[]):
        sweep_mod.sweep()  # no exception
