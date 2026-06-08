"""Provider registry keyed by ``agent.yaml`` protocol name."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fleetent.tools.image_gen.provider import ImageGenError, ImageGenProvider

if TYPE_CHECKING:
    from fleetent.model.resolver import ResolvedModelConfig

_PROVIDERS: dict[str, ImageGenProvider] = {}


def register(provider: ImageGenProvider) -> None:
    """Register a provider under its declared protocol."""
    _PROVIDERS[provider.protocol] = provider


async def dispatch(
    resolved: ResolvedModelConfig,
    prompt: str,
    *,
    size: str | None = None,
    api_key: str | None = None,
) -> bytes:
    """Dispatch to the provider matching resolved.protocol."""
    provider = _PROVIDERS.get(resolved.protocol)
    if provider is None:
        raise ImageGenError(
            f"no image generation provider for protocol '{resolved.protocol}'"
        )
    return await provider.generate(resolved, prompt, size=size, api_key=api_key)
