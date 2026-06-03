"""Runtime capability public API.

The agent execution core (`loop`) plus run-governance modules: in-session
compression (`context`), agent snapshots (`snapshot`), parallel sub-agents
(`sub_agent`/`sub_agent_lifecycle`), termination/budget/loop-detection,
cancellation, message hygiene, error classification, and tool guardrails.

Cross-package callers import the public symbols from here (or
``from fleetent.runtime import loop as agent_loop`` for module-style access),
not from the internal modules. Submodules reference each other directly (e.g.
``from fleetent.runtime.termination import ...``) to avoid an import cycle
through this ``__init__``; the ``loop`` <-> ``sub_agent`` edge stays a lazy
import to break their mutual dependency.

Importing ``fleetent.runtime.loop`` triggers ``import fleetent.tools`` as a
load-bearing side effect (built-in tool registration), so ``get_schemas()`` is
non-empty afterward.
"""

from fleetent.runtime.cancellation import CancellationChecker, CancelToken
from fleetent.runtime.loop import run, run_stream, run_sync
from fleetent.runtime.snapshot import load_active
from fleetent.runtime.sub_agent import SubAgentExecutor

__all__ = [
    "CancelToken",
    "CancellationChecker",
    "SubAgentExecutor",
    "load_active",
    "run",
    "run_stream",
    "run_sync",
]
