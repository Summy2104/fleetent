"""Re-export shim: moved to fleetent.runtime.tool_guardrails
(restructure-runtime-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes on fleetent.runtime.tool_guardrails, not on this shim —
``import *`` copies names, so patching the shim has no effect.
"""

from fleetent.runtime.tool_guardrails import *  # noqa: F401,F403
