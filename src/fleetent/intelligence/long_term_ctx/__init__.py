"""Compatibility shim for legacy `fleetent.intelligence.long_term_ctx` imports."""

from importlib import import_module
import sys

_legacy_long_term_ctx = import_module("fleetent.long_term_ctx")
sys.modules[__name__] = _legacy_long_term_ctx
