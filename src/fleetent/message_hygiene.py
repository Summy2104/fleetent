"""Re-export shim: moved to fleetent.runtime.message_hygiene
(restructure-runtime-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes on fleetent.runtime.message_hygiene, not on this shim —
``import *`` copies names, so patching the shim has no effect.
"""

from fleetent.runtime.message_hygiene import *  # noqa: F401,F403
