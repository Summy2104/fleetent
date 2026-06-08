"""OpenAI Images API provider (protocol: openai_image_generation)."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from openai import AsyncOpenAI, Omit, omit

from fleetent.tools.image_gen.provider import ImageGenError, ImageGenProvider, _fetch_url

if TYPE_CHECKING:
    from fleetent.model.resolver import ResolvedModelConfig

from fleetent.tools.image_gen import registry

_DEFAULT_TIMEOUT_SECONDS: float = 120.0


def _build_client(endpoint: str, api_key: str | None = None) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=endpoint, api_key=api_key or "image-gen")


class OpenAIImagesProvider(ImageGenProvider):
    """Calls /v1/images/generations (openai_image_generation protocol)."""

    @property
    def protocol(self) -> str:
        return "openai_image_generation"

    async def generate(
        self,
        resolved: ResolvedModelConfig,
        prompt: str,
        *,
        size: str | None = None,
        api_key: str | None = None,
    ) -> bytes:
        if not resolved.endpoint or not resolved.model:
            raise ImageGenError("openai_image_generation requires endpoint and model")

        client = _build_client(resolved.endpoint, api_key)
        size_arg: str | Omit = size if size is not None else omit
        try:
            response = await client.images.generate(
                model=resolved.model,
                prompt=prompt,
                response_format="b64_json",
                size=size_arg,
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            raise ImageGenError(f"images endpoint call failed: {exc}") from exc

        data = getattr(response, "data", None)
        if not data:
            raise ImageGenError("images endpoint returned no image data")
        image = data[0]

        b64 = getattr(image, "b64_json", None)
        if b64:
            try:
                return base64.b64decode(b64, validate=True)
            except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
                raise ImageGenError(f"invalid b64_json in images response: {exc}") from exc

        url = getattr(image, "url", None)
        if url:
            try:
                return await _fetch_url(url)
            except Exception as exc:
                raise ImageGenError(f"failed to fetch generated image url: {exc}") from exc

        raise ImageGenError("images response had neither b64_json nor url")


registry.register(OpenAIImagesProvider())
