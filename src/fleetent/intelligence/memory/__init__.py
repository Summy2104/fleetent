"""Compatibility shim for legacy `fleetent.intelligence.memory` imports."""

from importlib import import_module
import sys

_legacy_memory = import_module("fleetent.memory")
sys.modules[__name__] = _legacy_memory
