from __future__ import annotations

import os

DEFAULT_FORWARDER_PORT = 8767
DEFAULT_FORWARDER_DOMAIN = "internal"


def _forwarder_host(node_id: str) -> str:
    override = os.environ.get("FLEETENT_FORWARDER_HOST_OVERRIDE", "")
    return override if override else f"{node_id}.{DEFAULT_FORWARDER_DOMAIN}"


def forwarder_base_url(node_id: str) -> str:
    return f"http://{_forwarder_host(node_id)}:{DEFAULT_FORWARDER_PORT}"


def forwarder_ws_url(node_id: str) -> str:
    return f"ws://{_forwarder_host(node_id)}:{DEFAULT_FORWARDER_PORT}"
