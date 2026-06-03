"""Re-export shim: context manager moved to fleetent.runtime.context
(restructure-runtime-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes on fleetent.runtime.context, not on this
shim — ``import *`` copies names, so patching the shim has no effect.
"""

from fleetent.runtime.context import *  # noqa: F401,F403
