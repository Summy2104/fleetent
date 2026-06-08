"""Compatibility facade for legacy knowledge-base operations imports."""

from __future__ import annotations

import sys
from importlib import import_module
from typing import TYPE_CHECKING

_legacy_operations = import_module("fleetent.intelligence.knowledge_base.operations")
if TYPE_CHECKING:
    from fleetent.intelligence.knowledge_base.operations import *  # noqa: F401,F403

# Keep compatibility module identity with the legacy implementation so monkeypatches on
# fleetent.intelligence.knowledge_base.operations also affect this path.
sys.modules[__name__] = _legacy_operations

# Re-export public names for static analyzers/importers that inspect this module object.
globals().update(
    {
        name: getattr(_legacy_operations, name)
        for name in dir(_legacy_operations)
        if not name.startswith("_")
    }
)
