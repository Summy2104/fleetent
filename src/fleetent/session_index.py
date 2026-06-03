"""Re-export shim: session index moved to fleetent.session.index
(runtime-package-blueprint). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes (e.g. DB_PATH) on fleetent.session.index,
not on this shim — ``import *`` copies names, so patching the shim has no effect.
"""

from fleetent.session.index import *  # noqa: F401,F403
