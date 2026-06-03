"""Re-export shim: provider health moved to fleetent.model.provider_health
(restructure-model-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes (e.g. _cache) on
fleetent.model.provider_health, not on this shim — ``import *`` copies names,
so patching the shim has no effect.
"""

from fleetent.model.provider_health import *  # noqa: F401,F403
