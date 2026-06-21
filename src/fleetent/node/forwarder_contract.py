from __future__ import annotations

DEFAULT_FORWARDER_PORT = 8786
DEFAULT_FORWARDER_DOMAIN = "internal"


def forwarder_base_url(node_id: str) -> str:
    return f"http://{node_id}.{DEFAULT_FORWARDER_DOMAIN}:{DEFAULT_FORWARDER_PORT}"


def forwarder_ws_url(node_id: str) -> str:
    return f"ws://{node_id}.{DEFAULT_FORWARDER_DOMAIN}:{DEFAULT_FORWARDER_PORT}"
