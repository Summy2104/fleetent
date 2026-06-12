"""Re-export shim — outbound primitives moved to fleetent.outbound (top-level base infra)."""

from fleetent.outbound import (  # noqa: F401
    is_reachable,
    send_file_to,
    send_to,
)

__all__ = ["is_reachable", "send_file_to", "send_to"]
