"""Re-export shim: moved to fleetent.runtime.termination
(restructure-runtime-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes on fleetent.runtime.termination, not on this shim —
``import *`` copies names, so patching the shim has no effect.
"""

from fleetent.runtime.termination import *  # noqa: F401,F403
