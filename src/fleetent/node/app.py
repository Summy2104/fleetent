from __future__ import annotations

import sys
import time

from fleetent.node.backend import LocalProcessBackend
from fleetent.node.config import ConfigError, load_config
from fleetent.node.provider import PlatformApiDesiredStateProvider
from fleetent.node.reconcile import NodeReconciler


def main() -> None:
    """Run the node supervisor polling loop until interrupted."""
    try:
        config = load_config()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    provider = PlatformApiDesiredStateProvider(config)
    backend = LocalProcessBackend(config)
    reconciler = NodeReconciler(config, backend)
    try:
        while True:
            reconciler.reconcile(provider.fetch())
            time.sleep(config.interval_seconds)
    except KeyboardInterrupt:
        return
