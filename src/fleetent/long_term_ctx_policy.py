"""Compatibility shim for legacy ``fleetent.long_term_ctx_policy`` imports."""

import sys
from importlib import import_module

_legacy_long_term_ctx_policy = import_module("fleetent.long_term_ctx._policy")
sys.modules[__name__] = _legacy_long_term_ctx_policy
