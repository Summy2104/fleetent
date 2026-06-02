"""Five-layer cost/usage budget control (AR18): task/session/user/agent/global.

AR2's `budget.py` is the per-run turns/tokens budget; its cost dimension was
review-removed (and is test-guarded), so the cost machinery lives here. This
module adds cross-run, layered budgets persisted in `users.db` keyed by
(scope, key, period), reusing AR2's NO_LIMIT sentinel and turns/tokens
accumulation semantics while owning the cost dimension and per-token pricing.
Standard-library sqlite3 only; injectable clock and DB_PATH for tests.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from fleetent.budget import NO_LIMIT
from fleetent.user_store import DB_PATH as DB_PATH  # noqa: F401 — re-export for monkeypatch

# Per-token USD pricing (prompt, completion). Conservative placeholders; ops can
# extend MODEL_PRICING. DEFAULT_PRICING applies to unknown / None models.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (1.5e-5, 7.5e-5),
    "claude-sonnet-4-6": (3.0e-6, 1.5e-5),
    "claude-haiku-4-5": (8.0e-7, 4.0e-6),
    "gpt-4o": (2.5e-6, 1.0e-5),
}
DEFAULT_PRICING: tuple[float, float] = (1.0e-6, 2.0e-6)


def _price(model: str | None) -> tuple[float, float]:
    return MODEL_PRICING.get(model, DEFAULT_PRICING) if model else DEFAULT_PRICING


class BudgetScope(StrEnum):
    task = "task"
    session = "session"
    user = "user"
    agent = "agent"
    global_ = "global"


# Narrow → wide. task is per-run (AR2); the rest are cross-run (persisted here).
SCOPE_ORDER: tuple[BudgetScope, ...] = (
    BudgetScope.task,
    BudgetScope.session,
    BudgetScope.user,
    BudgetScope.agent,
    BudgetScope.global_,
)
CROSS_RUN_SCOPES: tuple[BudgetScope, ...] = (
    BudgetScope.session,
    BudgetScope.user,
    BudgetScope.agent,
    BudgetScope.global_,
)

# Sentinel key for the single global bucket (no natural id).
GLOBAL_KEY = "__global__"


class BudgetWindow(StrEnum):
    lifetime = "lifetime"
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


_DEFAULT_WINDOW: dict[BudgetScope, BudgetWindow] = {
    BudgetScope.session: BudgetWindow.lifetime,
    BudgetScope.user: BudgetWindow.weekly,
    BudgetScope.agent: BudgetWindow.weekly,
    BudgetScope.global_: BudgetWindow.monthly,
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
    """Mutable accumulator: turns/tokens (AR2 semantics) + the cost dimension."""

    turns: int = 0
    tokens: int = 0
    cost_usd: float = 0.0

    def add(self, prompt_tokens: int, completion_tokens: int, model: str | None = None) -> None:
        self.turns += 1
        self.tokens += prompt_tokens + completion_tokens
        prompt_price, completion_price = _price(model)
        self.cost_usd += prompt_tokens * prompt_price + completion_tokens * completion_price


@dataclass(frozen=True)
class ScopeBudget:
    """A scope's caps across turns/tokens/cost. NO_LIMIT means unlimited."""

    max_turns: int = NO_LIMIT
    max_tokens: int = NO_LIMIT
    max_cost_usd: float = NO_LIMIT

    def exhausted_dimension(self, usage: ScopeUsage) -> str | None:
        """First dimension (turns→tokens→cost) at/over its cap, else None."""
        if self.max_turns != NO_LIMIT and usage.turns >= self.max_turns:
            return "turns"
        if self.max_tokens != NO_LIMIT and usage.tokens >= self.max_tokens:
            return "tokens"
        if self.max_cost_usd != NO_LIMIT and usage.cost_usd >= self.max_cost_usd:
            return "cost"
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
            b.max_turns != NO_LIMIT or b.max_tokens != NO_LIMIT or b.max_cost_usd != NO_LIMIT
            for b in self.per_scope.values()
        )

    @classmethod
    def from_settings(cls, settings: object | None = None) -> LayeredBudgetConfig:
        from fleetent.config import Settings

        s = settings if settings is not None else Settings()
        per: dict[BudgetScope, ScopeBudget] = {}
        for scope in CROSS_RUN_SCOPES:
            name = scope.value
            per[scope] = ScopeBudget(
                max_turns=getattr(s, f"agent_budget_{name}_turns", NO_LIMIT),
                max_tokens=getattr(s, f"agent_budget_{name}_tokens", NO_LIMIT),
                max_cost_usd=getattr(s, f"agent_budget_{name}_cost_usd", float(NO_LIMIT)),
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
              cost_usd  REAL NOT NULL,
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
        model: str | None = None,
        *,
        now: datetime,
    ) -> None:
        if scope not in CROSS_RUN_SCOPES:
            raise ValueError(f"scope {scope} is per-run (AR2), not persisted")
        delta = ScopeUsage()
        delta.add(prompt_tokens, completion_tokens, model)
        period = self._period(scope, now)
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO budget_usage (scope, key, period, turns, tokens, cost_usd)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, key, period) DO UPDATE SET
                  turns = turns + excluded.turns,
                  tokens = tokens + excluded.tokens,
                  cost_usd = cost_usd + excluded.cost_usd
                """,
                (scope.value, key, period, delta.turns, delta.tokens, delta.cost_usd),
            )

    def get(self, scope: BudgetScope, key: str, *, now: datetime) -> ScopeUsage:
        period = self._period(scope, now)
        with _conn() as conn:
            row = conn.execute(
                "SELECT turns, tokens, cost_usd FROM budget_usage "
                "WHERE scope = ? AND key = ? AND period = ?",
                (scope.value, key, period),
            ).fetchone()
        if row is None:
            return ScopeUsage()
        return ScopeUsage(turns=row[0], tokens=row[1], cost_usd=row[2])


def _scope_keys(
    session_id: str | None, user_id: str | None, agent_id: str | None
) -> dict[BudgetScope, str | None]:
    return {
        BudgetScope.session: session_id,
        BudgetScope.user: user_id,
        BudgetScope.agent: agent_id,
        BudgetScope.global_: GLOBAL_KEY,
    }


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
        from fleetent.termination import StopReason

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


@dataclass(frozen=True)
class BudgetHeadroom:
    """Read-only snapshot of cost headroom across the configured cost-capped scopes."""

    cost_remaining_ratio: float
    tightest_scope: str | None


def headroom(
    config: LayeredBudgetConfig,
    store: BudgetStore,
    session_id: str | None,
    user_id: str | None,
    agent_id: str | None,
    *,
    clock: Callable[[], datetime],
) -> BudgetHeadroom:
    """Tightest cost headroom over scopes that have a cost cap and a present key.

    Returns (1.0, None) when no scope has a cost cap (or none has a key)."""
    now = clock()
    keys = _scope_keys(session_id, user_id, agent_id)
    tightest_ratio = 1.0
    tightest_scope: str | None = None
    for scope in CROSS_RUN_SCOPES:
        key = keys.get(scope)
        if key is None:
            continue
        cap = config.for_scope(scope).max_cost_usd
        if cap == NO_LIMIT or cap <= 0:
            continue
        used = store.get(scope, key, now=now).cost_usd
        ratio = max(0.0, (cap - used) / cap)
        if ratio < tightest_ratio:
            tightest_ratio = ratio
            tightest_scope = scope.value
    return BudgetHeadroom(cost_remaining_ratio=tightest_ratio, tightest_scope=tightest_scope)


def utc_now() -> datetime:
    """Default clock: timezone-aware UTC now (injectable in callers/tests)."""
    return datetime.now(UTC)
