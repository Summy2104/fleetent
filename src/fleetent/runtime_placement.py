"""Single source of truth for node-managed runtime detection (agent-hosted-im).

The agent process learns it is node-managed from exactly one signal that node
*actually delivers* into the agent ``.env``: ``FLEETENT_NODE_LOOPBACK_URL`` (written
by ``node/reconcile.py`` _write_home). The previously-used trio
``FLEETENT_NODE_ID`` / ``FLEETENT_NODE_PLATFORM_URL`` / ``FLEETENT_NODE_SERVICE_KEY``
was never written to a containerized agent's ``.env`` (containers get ``--env-file``
only, no host-env inheritance), so keying "am I managed?" off it silently mis-detected
container agents as standalone — the AAA-8208 root cause. Every managed-vs-standalone
decision MUST route through :func:`is_managed`.
"""

import os

_LOOPBACK_ENV = "FLEETENT_NODE_LOOPBACK_URL"


def is_managed() -> bool:
    """Whether this agent process runs under node-managed placement.

    True iff the delivered ``FLEETENT_NODE_LOOPBACK_URL`` signal is present and
    non-blank in the process environment.
    """
    return bool(os.environ.get(_LOOPBACK_ENV, "").strip())
