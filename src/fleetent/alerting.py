"""Pure alerting logic: threshold×duration evaluation, maintenance windows,
suppression, escalation. No IO — operates on samples/rules/alerts passed in, so it is
trivially testable. Channel sending + retries live in the API layer behind seams.
"""

import datetime
from typing import Any

_COMPARATORS = {
    ">": lambda v, t: v > t,
    ">=": lambda v, t: v >= t,
    "<": lambda v, t: v < t,
    "<=": lambda v, t: v <= t,
}


def _parse(ts: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(ts)


def breach(value: float, comparator: str, threshold: float) -> bool:
    return _COMPARATORS[comparator](value, threshold)


def evaluate(rule: dict[str, Any], samples: list[dict[str, Any]], now: datetime.datetime) -> bool:
    """Fire only when every sample in the [now-for_seconds, now] window breaches AND the
    window is actually covered (oldest in-window sample is >= for_seconds old). A single
    recent spike does not satisfy the sustained-duration requirement.
    """
    if not rule.get("enabled", 1):
        return False
    for_seconds = int(rule.get("for_seconds", 0))
    window_start = now - datetime.timedelta(seconds=for_seconds)
    in_window = [s for s in samples if _parse(s["ts"]) >= window_start]
    if not in_window:
        return False
    if not all(breach(s["value"], rule["comparator"], rule["threshold"]) for s in in_window):
        return False
    if for_seconds > 0:
        # Coverage: the breach must already be active at the window start. Require a
        # sample at/before window_start that also breaches; otherwise the duration is
        # unproven (a recent spike, or monitoring only just began).
        before = [s for s in samples if _parse(s["ts"]) <= window_start]
        if not before:
            return False
        latest_before = max(before, key=lambda s: _parse(s["ts"]))
        if not breach(latest_before["value"], rule["comparator"], rule["threshold"]):
            return False
    return True


def in_maintenance(
    windows: list[dict[str, Any]], target: str | None, now: datetime.datetime
) -> bool:
    for w in windows:
        if w.get("target") not in (None, target):
            continue
        if _parse(w["start_ts"]) <= now <= _parse(w["end_ts"]):
            return True
    return False


def is_suppressed(target: str | None, down_hosts: set[str]) -> bool:
    """Suppress a container/process alert when its host is already down.

    Convention: target like ``host:h1`` or ``host:h1/container:c1``. A target is
    suppressed when its host segment is in ``down_hosts`` and the target is not the
    host alert itself.
    """
    if not target or not down_hosts:
        return False
    host = target.split("/", 1)[0]
    return host in down_hosts and target != host


def should_escalate(
    alert: dict[str, Any], now: datetime.datetime, escalate_after_seconds: int
) -> bool:
    """critical alert that has been notified but not acked for too long."""
    if alert.get("severity") != "critical":
        return False
    if alert.get("status") not in {"firing", "notified"}:
        return False
    fired = _parse(alert["fired_at"])
    return (now - fired).total_seconds() >= escalate_after_seconds
