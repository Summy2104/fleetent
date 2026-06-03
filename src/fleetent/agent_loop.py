"""Re-export shim: agent loop moved to fleetent.runtime.loop
(restructure-runtime-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes (e.g. get_async_client_and_config,
get_schemas, match_skill, maybe_compress, extract_and_update, run) on
fleetent.runtime.loop, not on this shim — ``import *`` copies names, so
patching the shim has no effect.
"""

from fleetent.runtime.loop import *  # noqa: F401,F403
