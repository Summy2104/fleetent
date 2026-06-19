"""Deprecated console-script shims."""

from __future__ import annotations

import sys


def fleetent_admin_shim() -> None:
    """Forward the deprecated ``fleetent-admin`` entrypoint to ``fleetent admin``."""
    print("Deprecated: 'fleetent-admin' → use 'fleetent admin'.", file=sys.stderr)
    sys.argv = ["fleetent", "admin", *sys.argv[1:]]

    from fleetent.__main__ import main

    main()


def fleetent_node_shim() -> None:
    """Forward the deprecated ``fleetent-node`` entrypoint to ``fleetent node start``."""
    print("Deprecated: 'fleetent-node' → use 'fleetent node start'.", file=sys.stderr)
    sys.argv = ["fleetent", "node", "start", *sys.argv[1:]]

    from fleetent.__main__ import main

    main()
