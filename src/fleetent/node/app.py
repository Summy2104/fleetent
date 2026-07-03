from __future__ import annotations

import sys
import time
import os
from threading import Thread

from fleetent.node.backend import create_process_backend
from fleetent.node.config import ConfigError, load_config
from fleetent.node.forwarder import build_app as build_forwarder_app
from fleetent.node.forwarder_contract import DEFAULT_FORWARDER_PORT
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

    from fleetent.logging_setup import setup_process_logging

    setup_process_logging(log_format=os.getenv("LOG_FORMAT", "console"))

    from fleetent.build_info import log_service_startup

    log_service_startup("node")
    provider = PlatformApiDesiredStateProvider(config)
    backend = create_process_backend(config)
    reconciler = NodeReconciler(config, backend)
    # agent-hosted-im: node no longer hosts an IM edge. Each agent self-hosts its own Slack/
    # Telegram connection (spawned without --no-im) and resolves IM identities/addresses via the
    # node loopback forwarder endpoints. Node only spawns/monitors agent processes + forwards.
    forwarder_server, forwarder_thread = _start_forwarder(config, backend)
    try:
        while True:
            desired_state = provider.fetch()
            reconciler.reconcile(desired_state)
            time.sleep(config.interval_seconds)
    except KeyboardInterrupt:
        return
    finally:
        forwarder_server.should_exit = True
        forwarder_thread.join(timeout=5)
