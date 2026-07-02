"""Inbound IM dispatch seam (agent-hosted-im).

The agent self-hosts its IM connection in all placements, so inbound messages route locally
through :func:`fleetent.im_gateway.normalizer.route`. This thin indirection lets the Slack /
Telegram adapters call one entry point without importing the normalizer directly at module top.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fleetent.im_gateway.normalizer import NormalizedMessage


async def dispatch(msg: NormalizedMessage) -> None:
    from fleetent.im_gateway import normalizer

    await normalizer.route(msg)
