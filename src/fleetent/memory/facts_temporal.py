"""Temporal-intent enum → concrete expiry boundary.

The LLM only classifies a fact's time sense (``today`` / ``this_week`` / ``none``
…) — a semantic judgement it is good at.  The actual calendar arithmetic lives
here, where ``now`` and the calendar are known, so dates are computed
deterministically instead of being hallucinated by the model.

Timezone: boundaries are computed in UTC for now.  The user's timezone is not yet
injected into the agent; once it is, pass a tz-aware ``now`` in that zone.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

TemporalIntent = Literal["none", "today", "tomorrow", "this_week", "this_month"]

# Recognized intents that carry an expiry boundary (everything else → no expiry).
_KNOWN: frozenset[str] = frozenset({"today", "tomorrow", "this_week", "this_month"})


def temporal_boundary(intent: str, now: datetime) -> datetime | None:
    """Return the expiry instant for a temporal intent, or None for no boundary.

    ``none`` and any unrecognized intent return None (the fact has no time-based
    expiry and follows the relation's default lifetime).  Recognized intents
    resolve to the END (23:59:59) of the relevant day.
    """
    if intent not in _KNOWN:
        return None
    if intent == "today":
        return _end_of_day(now)
    if intent == "tomorrow":
        return _end_of_day(now + timedelta(days=1))
    if intent == "this_week":
        # ISO weekday: Mon=1 … Sun=7; advance to Sunday.
        days_to_sunday = 7 - now.isoweekday()
        return _end_of_day(now + timedelta(days=days_to_sunday))
    if intent == "this_month":
        return _end_of_day(_last_day_of_month(now))
    return None  # unreachable, kept for type-checker exhaustiveness


def _end_of_day(when: datetime) -> datetime:
    return when.replace(hour=23, minute=59, second=59, microsecond=0)


def _last_day_of_month(when: datetime) -> datetime:
    if when.month == 12:
        first_next = when.replace(
            year=when.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    else:
        first_next = when.replace(
            month=when.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    return first_next - timedelta(days=1)
