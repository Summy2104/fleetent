"""Retired admin CLI package.

This path used to host the legacy platform admin CLI. Keep it non-importable so
tests and callers do not silently resolve an empty namespace package from stale
directories or bytecode caches.
"""

raise ModuleNotFoundError("No module named 'fleetent.platform.admin_cli'")
