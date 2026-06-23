"""E2E: cron task fires in standalone agent and writes run-state back to agent_state.db.

Probe results (task 1.3):
- Pre-seeded notify task (interval=2s, user_id="default", deliver/origin=None).
- No LLM call, no connectors — _record_run always writes last_status="ok".
- Observation: poll last_run_at until populated, assert last_status=="ok".
"""

from __future__ import annotations

from tests.e2e._cron_helpers import CronProbe, _poll_run_state, cron_probe  # noqa: F401


def test_cron_task_fires_and_writes_run_state(cron_probe: CronProbe) -> None:
    row = _poll_run_state(cron_probe.state_db_path, cron_probe.task_id)

    assert row["last_run_at"] is not None, "scheduler did not write last_run_at"
    assert row["last_status"] == "ok", f"unexpected status: {row['last_status']!r}, error={row.get('last_error')!r}"
