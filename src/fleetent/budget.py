"""Three-dimensional iteration budget (AR2): turns / tokens / USD cost.

This module is the published metering contract for wave 3 (AR18 layered budgets,
MR2 cost-aware routing): the dimension set ``{turns, tokens, cost_usd}`` and the
``BudgetUsage.add(...)`` accumulation口径 are stable. A frozen ``BudgetConfig``
carries the per-run limits; a mutable ``BudgetUsage`` is the single accumulation
entry point; ``BudgetChecker`` plugs the "any dimension exhausted" judgement into
the AR1 termination framework via ``StopReason.budget_exceeded``.

Dollar cost is an *estimate* for loss-prevention, not billing: it uses a static,
injectable in-module price table — no cloud pricing API (data sovereignty).
"""

from __future__ import annotations

from dataclasses import dataclass

from fleetent.termination import LoopState, StopReason

# Sentinel for an "unlimited" dimension. A dimension set to this never triggers
# exhaustion regardless of usage.
NO_LIMIT = -1

# Static price table: model → (input_price, output_price) in USD per 1K tokens.
# Module-level and monkeypatchable for tests; never queries a cloud pricing API.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5": (0.003, 0.015),
    "claude-haiku-4-5": (0.001, 0.005),
    "claude-opus-4-5": (0.015, 0.075),
}

# Fallback for models not in MODEL_PRICING. Conservative (never zero): a model
# off the table must still incur cost, otherwise the cost dimension is toothless
# for it. Set at/above the priciest listed model — "off-table fallback: 宁高勿漏".
DEFAULT_PRICING: tuple[float, float] = (0.015, 0.075)

# Order in which dimensions are reported when several are simultaneously over.
_DIMENSION_ORDER: tuple[str, str, str] = ("turns", "tokens", "cost_usd")


@dataclass(frozen=True)
class BudgetConfig:
    """Per-run budget caps across three dimensions (frozen: config never mutates).

    Any dimension set to ``NO_LIMIT`` is unlimited and never triggers exhaustion.
    """

    max_turns: int
    max_tokens: int
    max_cost_usd: float

    def exhausted_dimension(self, usage: BudgetUsage) -> str | None:
        """Return the first dimension (turns→tokens→cost_usd) at/over its cap, else None."""
        if self.max_turns != NO_LIMIT and usage.turns >= self.max_turns:
            return "turns"
        if self.max_tokens != NO_LIMIT and usage.tokens >= self.max_tokens:
            return "tokens"
        if self.max_cost_usd != NO_LIMIT and usage.cost_usd >= self.max_cost_usd:
            return "cost_usd"
        return None


@dataclass
class BudgetUsage:
    """Mutable per-run accumulator. ``add`` is the sole accumulation entry point.

    Only main-loop LLM calls made to advance the user's task call ``add``; system
    internal calls (compression, the grace call itself) do not flow through here
    (design D4), so they are exempt by construction.
    """

    turns: int = 0
    tokens: int = 0
    cost_usd: float = 0.0

    def add(self, prompt_tokens: int, completion_tokens: int, model: str) -> None:
        """Accumulate one main-loop turn: +1 turn, +tokens, +cost estimated from price table."""
        self.turns += 1
        self.tokens += prompt_tokens + completion_tokens
        in_price, out_price = MODEL_PRICING.get(model, DEFAULT_PRICING)
        self.cost_usd += (prompt_tokens / 1000.0) * in_price + (
            completion_tokens / 1000.0
        ) * out_price


class BudgetChecker:
    """AR1 termination checker: stop with ``budget_exceeded`` when any dimension is over.

    Records the triggering dimension on ``triggered_dimension`` so the loop can
    write it to the trace (design D6).
    """

    def __init__(self, config: BudgetConfig, usage: BudgetUsage) -> None:
        self._config = config
        self._usage = usage
        self.triggered_dimension: str | None = None

    def check(self, state: LoopState) -> StopReason | None:
        dimension = self._config.exhausted_dimension(self._usage)
        if dimension is not None:
            self.triggered_dimension = dimension
            return StopReason.budget_exceeded
        return None


def _grace_defaults() -> tuple[float, int]:
    """Grace-call ratio/floor defaults from Settings (env-configurable). Lazy import
    keeps this module import-light, mirroring termination._default_config."""
    from fleetent.config import Settings

    s = Settings()
    return s.agent_grace_call_token_ratio, s.agent_grace_call_min_tokens


def grace_max_tokens(
    max_tokens: int,
    ratio: float | None = None,
    floor: int | None = None,
) -> int:
    """Reserved grace-call token cap = max(round(max_tokens * ratio), floor).

    A small main budget — or an unlimited (``NO_LIMIT``) one — falls back to the
    floor so the grace call still gets a usable cap to write a real summary (D3).
    ratio/floor default from Settings when omitted (injectable for tests).
    """
    if ratio is None or floor is None:
        default_ratio, default_floor = _grace_defaults()
        ratio = default_ratio if ratio is None else ratio
        floor = default_floor if floor is None else floor
    if max_tokens == NO_LIMIT:
        return floor
    return max(round(max_tokens * ratio), floor)
