from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fleetent.im_gateway.normalizer import NormalizedMessage

_dispatcher: Callable[["NormalizedMessage"], Awaitable[None]] | None = None


def set_inbound_dispatcher(
    dispatcher: Callable[["NormalizedMessage"], Awaitable[None]] | None,
) -> None:
    global _dispatcher
    _dispatcher = dispatcher


async def dispatch(msg: "NormalizedMessage") -> None:
    if _dispatcher is not None:
        await _dispatcher(msg)
        return
    from fleetent.im_gateway import normalizer

    await normalizer.route(msg)
