"""ImageGenProvider ABC, shared error type, and URL fetch helper."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from fleetent.model.resolver import ResolvedModelConfig

_DEFAULT_TIMEOUT_SECONDS: float = 120.0


class ImageGenError(Exception):
    """Raised when image generation fails for any reason."""


class ImageGenProvider(abc.ABC):
    """Abstract base for a pluggable image generation backend.

    Keyed by :attr:`protocol`, which must match a ``ModelTarget.protocol``
    value in ``agent.yaml``.
    """

    @property
    @abc.abstractmethod
    def protocol(self) -> str:
        """The ``agent.yaml`` protocol string this provider handles."""

    @abc.abstractmethod
    async def generate(
        self,
        resolved: ResolvedModelConfig,
        prompt: str,
        *,
        size: str | None = None,
        api_key: str | None = None,
    ) -> bytes:
        """Generate an image and return raw bytes, or raise ImageGenError."""


async def _fetch_url(url: str) -> bytes:
    """Download image bytes from a URL; raises ImageGenError on HTTP errors."""
    try:
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_SECONDS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPStatusError as exc:
        raise ImageGenError(f"failed to fetch image url {url}: {exc}") from exc
    except Exception as exc:
        raise ImageGenError(f"failed to fetch image url {url}: {exc}") from exc
