"""Shared platform→node forwarder addressing.

Single source of truth for resolving a node's forwarder dial URL so every
platform-originated call (live agent transport, skill backflow bundle capture)
reaches the node at the same address.

Priority: reported ``forward_host`` (DB) → ``FLEETENT_FORWARDER_HOST_OVERRIDE``
→ ``{node_id}.internal`` convention. The last two are owned by
``node.forwarder_contract``; the first (and the SSRF guard around it) lives here
because it depends on platform state (``node_store``).
"""

from __future__ import annotations

import ipaddress
import logging
import re

from fleetent.node.forwarder_contract import (
    DEFAULT_FORWARDER_PORT,
    forwarder_base_url,
    forwarder_ws_url,
)
from fleetent.platform.node_management import node_store

_logger = logging.getLogger(__name__)

# RFC-1123 hostname: dot-separated labels of [A-Za-z0-9-], each 1-63 chars, not
# starting/ending with a hyphen; total length <= 253. Anchored, so any value with
# URL-smuggling characters (/, ?, #, @, :, whitespace, _) fails to match.
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)


def is_valid_forward_host(host: str) -> bool:
    """Whether a node-reported forward_host is safe to interpolate into a dial URL.

    The value is self-reported by the node and spliced into ``http://{host}:port``.
    Without this guard a value carrying URL-smuggling characters (``@``, ``/``,
    ``?``, ``#``, ``:``, whitespace) could redirect the platform's request to a
    different host (SSRF). Accept only a bare IPv4 literal or RFC-1123 hostname.
    Loopback/private addresses are intentionally allowed — colocated on-prem nodes
    legitimately advertise ``127.0.0.1`` or internal IPs.
    """
    try:
        return ipaddress.ip_address(host).version == 4
    except ValueError:
        return bool(_HOSTNAME_RE.match(host))


def resolve_forwarder_base_url(node_id: str) -> str:
    """Resolve the HTTP base URL for a node's forwarder, honoring forward_host."""
    host = node_store.get_forward_host(node_id)
    if host and is_valid_forward_host(host):
        return f"http://{host}:{DEFAULT_FORWARDER_PORT}"
    if host:
        _logger.warning("ignoring malformed reported forward_host %r for node %s", host, node_id)
    return forwarder_base_url(node_id)


def resolve_forwarder_ws_url(node_id: str) -> str:
    """Resolve the WebSocket base URL for a node's forwarder, honoring forward_host."""
    host = node_store.get_forward_host(node_id)
    if host and is_valid_forward_host(host):
        return f"ws://{host}:{DEFAULT_FORWARDER_PORT}"
    if host:
        _logger.warning("ignoring malformed reported forward_host %r for node %s", host, node_id)
    return forwarder_ws_url(node_id)
