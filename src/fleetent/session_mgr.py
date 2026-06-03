"""Re-export shim: session manager moved to fleetent.session.manager
(runtime-package-blueprint). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes (e.g. SESSIONS_DIR) on fleetent.session.manager,
not on this shim — ``import *`` copies names, so patching the shim has no effect.
"""

from fleetent.session.manager import *  # noqa: F401,F403
