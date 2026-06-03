"""Re-export shim: moved to fleetent.runtime.error_classifier
(restructure-runtime-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes on fleetent.runtime.error_classifier, not on this shim —
``import *`` copies names, so patching the shim has no effect.
"""

from fleetent.runtime.error_classifier import *  # noqa: F401,F403
