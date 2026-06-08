"""Compatibility shim for legacy `fleetent.intelligence.reflection` imports."""

from __future__ import annotations

import sys
from importlib import import_module

_legacy_reflection = import_module("fleetent.reflection.reflection")
sys.modules[__name__] = _legacy_reflection
