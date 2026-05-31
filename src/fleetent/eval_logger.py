"""Compatibility shim for the observability eval logger."""

import sys

from fleetent.observability import eval_logger as _eval_logger
from fleetent.observability.eval_logger import TRACE_PATH, log, log_run

sys.modules[__name__] = _eval_logger

__all__ = ["TRACE_PATH", "log", "log_run"]
