"""Re-export shim: moved to fleetent.runtime.loop_detector
(restructure-runtime-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes on fleetent.runtime.loop_detector, not on this shim —
``import *`` copies names, so patching the shim has no effect.
"""

from fleetent.runtime.loop_detector import *  # noqa: F401,F403
