"""Compatibility shim for legacy `fleetent.intelligence.long_term_ctx_policy` imports."""

from importlib import import_module
import sys

_legacy_long_term_ctx_policy = import_module("fleetent.long_term_ctx._policy")
sys.modules[__name__] = _legacy_long_term_ctx_policy
