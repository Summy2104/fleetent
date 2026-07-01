from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fleetent.im_gateway.normalizer import NormalizedMessage

_dispatcher: Callable[[NormalizedMessage], Awaitable[None]] | None = None


def set_inbound_dispatcher(
    dispatcher: Callable[[NormalizedMessage], Awaitable[None]] | None,
) -> None:
    global _dispatcher
    _dispatcher = dispatcher


def get_inbound_dispatcher() -> Callable[[NormalizedMessage], Awaitable[None]] | None:
    """Return the injected inbound dispatcher, or None when not node-managed.

    A non-None value means a node process injected its forwarder (`set_inbound_dispatcher`),
    so callers running on the IM edge can detect managed placement without importing `node`.
    """
    return _dispatcher


async def dispatch(msg: NormalizedMessage) -> None:
    if _dispatcher is not None:
        await _dispatcher(msg)
        return
    from fleetent.im_gateway import normalizer

    await normalizer.route(msg)
