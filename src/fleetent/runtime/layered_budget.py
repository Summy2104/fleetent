"""Five-layer turns/tokens budget control (AR18): task/session/user/agent/global.

AR2's `budget.py` is the per-run turns/tokens budget. This module adds cross-run,
layered turns/tokens budgets persisted in `users.db` keyed by (scope, key, period),
reusing AR2's NO_LIMIT sentinel and turns/tokens accumulation semantics. The cost
dimension was dropped (post-review: cost tracking has no real meaning here), so
this is purely a usage (turns/tokens) governance layer. Standard-library sqlite3
only; injectable clock and DB_PATH for tests.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from fleetent.runtime.budget import NO_LIMIT
from fleetent.user_store import DB_PATH as DB_PATH  # noqa: F401 — re-export for monkeypatch


class BudgetScope(StrEnum):
    task = "task"
    session = "session"
    user = "user"
    agent = "agent"


# Narrow → wide. task is per-run (AR2); the rest are cross-run (persisted here).
# The global (cross-agent) scope was dropped: distributed per-agent processes have
# no shared runtime to aggregate a cross-agent total.
SCOPE_ORDER: tuple[BudgetScope, ...] = (
    BudgetScope.task,
    BudgetScope.session,
    BudgetScope.user,
    BudgetScope.agent,
)
CROSS_RUN_SCOPES: tuple[BudgetScope, ...] = (
    BudgetScope.session,
    BudgetScope.user,
    BudgetScope.agent,
)


class BudgetWindow(StrEnum):
    lifetime = "lifetime"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


_DEFAULT_WINDOW: dict[BudgetScope, BudgetWindow] = {
    BudgetScope.session: BudgetWindow.lifetime,
    BudgetScope.user: BudgetWindow.weekly,
    BudgetScope.agent: BudgetWindow.weekly,
}


def period_for(window: BudgetWindow, now: datetime) -> str:
    """Map a UTC `now` to the period key for a window (emergent reset via the key)."""
    if window is BudgetWindow.lifetime:
        return "lifetime"
    if window is BudgetWindow.daily:
        return now.strftime("%Y-%m-%d")
    if window is BudgetWindow.weekly:
        iso = now.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return now.strftime("%Y-%m")  # monthly


@dataclass
class ScopeUsage:
    """Mutable accumulator: turns/tokens (AR2 semantics)."""

    turns: int = 0
    tokens: int = 0

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.turns += 1
        self.tokens += prompt_tokens + completion_tokens


@dataclass(frozen=True)
class ScopeBudget:
    """A scope's caps across turns/tokens. NO_LIMIT means unlimited."""

    max_turns: int = NO_LIMIT
    max_tokens: int = NO_LIMIT

    def exhausted_dimension(self, usage: ScopeUsage) -> str | None:
        """First dimension (turns→tokens) at/over its cap, else None."""
        if self.max_turns != NO_LIMIT and usage.turns >= self.max_turns:
            return "turns"
        if self.max_tokens != NO_LIMIT and usage.tokens >= self.max_tokens:
            return "tokens"
        return None


@dataclass
class LayeredBudgetConfig:
    """Per-scope caps; an unconfigured scope is unlimited on every dimension."""

    per_scope: dict[BudgetScope, ScopeBudget] = field(default_factory=dict)

    def for_scope(self, scope: BudgetScope) -> ScopeBudget:
        return self.per_scope.get(scope, ScopeBudget())

    def has_any_cap(self) -> bool:
        """Whether any scope caps any dimension. False ⇒ layered budget is dormant
        (no checker, no store writes) so default deployments behave exactly as before."""
        return any(
            b.max_turns != NO_LIMIT or b.max_tokens != NO_LIMIT for b in self.per_scope.values()
        )

    @classmethod
    def from_settings(cls, settings: object | None = None) -> LayeredBudgetConfig:
        from fleetent.config import Settings

        s = settings if settings is not None else Settings()  # type: ignore[call-arg]
        return cls._from_source(s)

    @classmethod
    def from_governance(cls, governance: object) -> LayeredBudgetConfig:
        """Build from a per-agent GovernanceConfig (duck-typed: reads the same
        ``agent_budget_<scope>_{turns,tokens}`` attribute names as Settings)."""
        return cls._from_source(governance)

    @classmethod
    def _from_source(cls, src: object) -> LayeredBudgetConfig:
        per: dict[BudgetScope, ScopeBudget] = {}
        for scope in CROSS_RUN_SCOPES:
            name = scope.value
            per[scope] = ScopeBudget(
                max_turns=getattr(src, f"agent_budget_{name}_turns", NO_LIMIT),
                max_tokens=getattr(src, f"agent_budget_{name}_tokens", NO_LIMIT),
            )
        return cls(per_scope=per)


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budget_usage (
              scope     TEXT NOT NULL,
              key       TEXT NOT NULL,
              period    TEXT NOT NULL,
              turns     INTEGER NOT NULL,
              tokens    INTEGER NOT NULL,
              PRIMARY KEY (scope, key, period)
            )
            """
        )


class BudgetStore:
    """Cross-run usage accumulation keyed by (scope, key, period) in users.db.

    Only the four cross-run scopes persist; task scope is per-run (AR2) and is
    rejected. `period` is derived from each scope's window and an injected `now`,
    so a new period naturally starts a fresh row (emergent reset, no cron).
    """

    def __init__(self, windows: dict[BudgetScope, BudgetWindow] | None = None) -> None:
        self.windows = windows if windows is not None else dict(_DEFAULT_WINDOW)
        init_db()

    def _period(self, scope: BudgetScope, now: datetime) -> str:
        return period_for(self.windows.get(scope, _DEFAULT_WINDOW[scope]), now)

    def add(
        self,
        scope: BudgetScope,
        key: str,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        now: datetime,
    ) -> None:
        if scope not in CROSS_RUN_SCOPES:
            raise ValueError(f"scope {scope} is per-run (AR2), not persisted")
        delta = ScopeUsage()
        delta.add(prompt_tokens, completion_tokens)
        period = self._period(scope, now)
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO budget_usage (scope, key, period, turns, tokens)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(scope, key, period) DO UPDATE SET
                  turns = turns + excluded.turns,
                  tokens = tokens + excluded.tokens
                """,
                (scope.value, key, period, delta.turns, delta.tokens),
            )

    def get(self, scope: BudgetScope, key: str, *, now: datetime) -> ScopeUsage:
        period = self._period(scope, now)
        with _conn() as conn:
            row = conn.execute(
                "SELECT turns, tokens FROM budget_usage WHERE scope = ? AND key = ? AND period = ?",
                (scope.value, key, period),
            ).fetchone()
        if row is None:
            return ScopeUsage()
        return ScopeUsage(turns=row[0], tokens=row[1])


class LayeredBudgetChecker:
    """AR1 checker over the 4 cross-run scopes (narrow→wide). A scope with no key
    (e.g. CLI without session/user) is skipped — never bucketed under an empty key."""

    def __init__(
        self,
        config: LayeredBudgetConfig,
        store: BudgetStore,
        keys: dict[BudgetScope, str | None],
        *,
        clock: Callable[[], datetime],
    ) -> None:
        self._config = config
        self._store = store
        self._keys = keys
        self._clock = clock
        self.triggered_scope: str | None = None
        self.triggered_dimension: str | None = None

    def check(self, state: object) -> object | None:
        from fleetent.runtime.termination import StopReason

        now = self._clock()
        for scope in CROSS_RUN_SCOPES:
            key = self._keys.get(scope)
            if key is None:
                continue
            usage = self._store.get(scope, key, now=now)
            dimension = self._config.for_scope(scope).exhausted_dimension(usage)
            if dimension is not None:
                self.triggered_scope = scope.value
                self.triggered_dimension = dimension
                return StopReason.budget_exceeded
        return None


def utc_now() -> datetime:
    """Default clock: timezone-aware UTC now (injectable in callers/tests)."""
    return datetime.now(UTC)
