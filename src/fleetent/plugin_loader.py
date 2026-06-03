"""Re-export shim: plugin loader moved to fleetent.tools.plugin_loader
(restructure-tools-package). No logic here — remove once all imports migrate.

Note: monkeypatch module attributes (e.g. PLUGINS_DIR) on
fleetent.tools.plugin_loader, not on this shim.
"""

from fleetent.tools.plugin_loader import *  # noqa: F401,F403
from fleetent.tools.plugin_loader import PLUGINS_DIR, PluginMeta  # noqa: F401
