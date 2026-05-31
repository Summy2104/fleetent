"""Compatibility shim for the observability eval logger."""

import sys

from fleetent.observability import eval_logger as _eval_logger

sys.modules[__name__] = _eval_logger
