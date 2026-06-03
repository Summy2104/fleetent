"""Re-export shim: model router moved to fleetent.model.router
(restructure-model-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes (e.g. ROUTES, ROUTES_PATH, AsyncOpenAI,
OpenAI, _file_routes_cache) on fleetent.model.router, not on this shim —
``import *`` copies names, so patching the shim has no effect.
"""

from fleetent.model.router import *  # noqa: F401,F403
