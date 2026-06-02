"""Cost-aware routing (MR2): degrade to a cheaper route when budget is tight.

Consumes AR18's `BudgetHeadroom` scalar (cost_remaining_ratio) and turns it into
a route choice via a small two-tier policy: `normal` (route unchanged) or
`degrade` (resolve a configured cheaper `degrade_target` task_type instead).
Disabled by default and a None headroom is always `normal`, so the existing
routing path is byte-identical unless a deployment opts in. This module operates
on the routes dict duck-typed (no import of model_router → no cycle).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import structlog

from fleetent.layered_budget import BudgetHeadroom

if TYPE_CHECKING:
    from fleetent.config import Settings

logger = structlog.get_logger(__name__)


class CostAction(StrEnum):
    normal = "normal"
    degrade = "degrade"


@dataclass
class CostAwareRoutingPolicy:
    """Two-tier cost policy. `degrade_target=None` (default) makes `degrade`
    unreachable — cost-aware never silently lowers quality without an explicit
    target. Disabled or a None/ample headroom is always `normal`."""

    enabled: bool = False
    degrade_below: float = 0.2
    degrade_target: str | None = None

    def decide(self, headroom: BudgetHeadroom | None) -> CostAction:
        if not self.enabled or headroom is None or self.degrade_target is None:
            return CostAction.normal
        if headroom.cost_remaining_ratio < self.degrade_below:
            return CostAction.degrade
        return CostAction.normal

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> CostAwareRoutingPolicy:
        from fleetent.config import Settings

        s = settings if settings is not None else Settings()
        return cls(
            enabled=s.cost_aware_routing_enabled,
            degrade_below=s.cost_aware_degrade_below,
            degrade_target=s.cost_aware_degrade_target or None,
        )


def resolve_base_route(
    routes: dict[str, Any],
    task_type: str,
    headroom: BudgetHeadroom | None,
    policy: CostAwareRoutingPolicy | None = None,
) -> Any:
    """Return the base route for `task_type`, degraded to `degrade_target` when the
    policy decides so. `normal` (and unknown degrade_target) fall back to the usual
    `routes.get(task_type, routes["default"])` — byte-identical to plain routing."""
    pol = policy if policy is not None else CostAwareRoutingPolicy.from_settings()
    if pol.decide(headroom) is CostAction.degrade and pol.degrade_target is not None:
        target = pol.degrade_target
        if target not in routes:
            logger.warning("cost_aware_degrade_target_unknown", target=target)
        return routes.get(target, routes["default"])
    return routes.get(task_type, routes["default"])
