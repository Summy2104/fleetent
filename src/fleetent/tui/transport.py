"""Transport abstraction + WSTransport (peer-gone aware).

A ``Transport`` is the single seam the dispatch writes frames through, so the same
dispatch can later serve other transports (stdio/web). ``WSTransport`` wraps a
starlette WebSocket and (design D9) distinguishes *peer-gone* (client disconnected
— ``write`` returns ``False`` and the connection is torn down) from genuine I/O or
serialization errors (re-raised, never disguised as a clean disconnect).
"""

from typing import Any, Protocol, runtime_checkable

from starlette.websockets import WebSocketDisconnect

from fleetent.structured_logging import get_logger
from fleetent.tui import protocol as proto

_logger = get_logger("tui.transport")


@runtime_checkable
class Transport(Protocol):
    """A sink for outbound protocol frames."""

    async def write(self, obj: dict[str, Any]) -> bool:
        """Send one frame; return ``False`` if the peer is gone, ``True`` on success."""
        ...

    async def close(self) -> None:
        """Close the underlying connection (idempotent)."""
        ...


def _is_peer_gone(exc: BaseException) -> bool:
    """Classify an exception raised while sending as a client disconnect vs a real error."""
    if isinstance(exc, WebSocketDisconnect | ConnectionError):
        return True
    if isinstance(exc, RuntimeError):
        # starlette raises RuntimeError when sending after the socket has closed.
        msg = str(exc).lower()
        return "close" in msg or "disconnect" in msg or "after sending" in msg
    return False


class WSTransport:
    """``Transport`` over a starlette WebSocket."""

    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self._closed = False

    async def write(self, obj: dict[str, Any]) -> bool:
        if self._closed:
            return False
        try:
            await self._ws.send_text(proto.encode_frame(obj))
            return True
        except Exception as exc:
            if _is_peer_gone(exc):
                self._closed = True
                return False
            raise

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._ws.close()
        except Exception as exc:  # noqa: BLE001 — closing an already-gone socket is fine
            if not _is_peer_gone(exc):
                _logger.warn("ws_close_error", exception=exc)
