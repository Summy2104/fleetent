"""Re-export shim: moved to fleetent.runtime.sub_agent
(restructure-runtime-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes on fleetent.runtime.sub_agent, not on this shim —
``import *`` copies names, so patching the shim has no effect.
"""

from fleetent.runtime.sub_agent import *  # noqa: F401,F403
