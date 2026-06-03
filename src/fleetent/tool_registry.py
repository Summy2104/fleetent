"""Re-export shim: tool registry moved to fleetent.tools.registry
(restructure-tools-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes (e.g. _registry) on fleetent.tools.registry,
not on this shim — ``import *`` copies names, so patching the shim has no effect.
"""

from fleetent.tools.registry import *  # noqa: F401,F403
from fleetent.tools.registry import (  # noqa: F401
    ToolSchema,
    _registry,
    _risk_levels,
    get_effective_timeout,
    get_risk_level,
    is_self_truncating,
)
