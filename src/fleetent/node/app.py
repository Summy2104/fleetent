from __future__ import annotations

import sys
import time
from threading import Thread

from fleetent.node.backend import create_process_backend
from fleetent.node.config import ConfigError, load_config
from fleetent.node.forwarder import build_app as build_forwarder_app
from fleetent.node.forwarder_contract import DEFAULT_FORWARDER_PORT
from fleetent.node.im_edge import NodeIMEdgeHost
from fleetent.node.provider import PlatformApiDesiredStateProvider
from fleetent.node.reconcile import NodeReconciler


def _start_forwarder(config, backend) -> tuple[object, Thread]:
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(
            build_forwarder_app(config, backend),
            host="0.0.0.0",
            port=DEFAULT_FORWARDER_PORT,
            log_level="warning",
        )
    )
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def main() -> None:
    """Run the node supervisor polling loop until interrupted."""
    try:
        config = load_config()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    provider = PlatformApiDesiredStateProvider(config)
    backend = create_process_backend(config)
    reconciler = NodeReconciler(config, backend)
    im_edge_host = NodeIMEdgeHost(config, backend=backend)
    forwarder_server, forwarder_thread = _start_forwarder(config, backend)
    try:
        while True:
            desired_state = provider.fetch()
            reconciler.reconcile(desired_state)
            im_edge_host.reconcile(desired_state)
            time.sleep(config.interval_seconds)
    except KeyboardInterrupt:
        return
    finally:
        im_edge_host.close()
        forwarder_server.should_exit = True
        forwarder_thread.join(timeout=5)
