"""Client for a self-hosted, OpenAI-compatible images endpoint.

Mirrors the model_router philosophy: an OpenAI-compatible base_url pointed at
any self-hostable backend (SD-WebUI / ComfyUI / Flux behind a compat layer).
No cloud-hosted proprietary service (DALL·E / Midjourney) — data stays in-net.

Returns raw image bytes; the calling tool is responsible for persistence and
returning a short reference (never inline base64).
"""

import base64

import httpx
from openai import AsyncOpenAI, Omit, omit

from fleetent.config import Settings

# Long enough for diffusion backends, which may take seconds to minutes (D5).
_DEFAULT_TIMEOUT_SECONDS: float = 120.0


class ImageGenError(Exception):
    """Raised when image generation cannot produce bytes (unconfigured endpoint,
    endpoint error/timeout, or an unusable response)."""


def _build_client(settings: Settings) -> AsyncOpenAI:
    """Build an AsyncOpenAI bound to the configured images endpoint.

    Self-hosted endpoints often ignore the key; a non-empty placeholder keeps
    the SDK from rejecting the request before it reaches the backend.
    """
    return AsyncOpenAI(base_url=settings.image_gen_url, api_key="image-gen")


async def _fetch_url(url: str) -> bytes:
    """Fetch image bytes from an in-network URL (used when the backend returns
    a url instead of b64_json)."""
    async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_SECONDS) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def generate(
    prompt: str,
    *,
    size: str | None = None,
    settings: Settings | None = None,
) -> bytes:
    """Generate an image from a text prompt and return raw image bytes.

    Prefers `response_format="b64_json"` and decodes it; if the backend returns
    a url instead, fetches the bytes from that in-network url. Any failure is
    raised as ImageGenError for the caller to normalize.
    """
    settings = settings or Settings()  # type: ignore[call-arg]
    if not settings.image_gen_url:
        raise ImageGenError("image generation endpoint not configured (image_gen_url is empty)")

    client = _build_client(settings)
    size_arg: str | Omit = size if size is not None else omit
    try:
        response = await client.images.generate(
            model=settings.image_gen_model,
            prompt=prompt,
            response_format="b64_json",
            size=size_arg,
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # endpoint error / timeout — normalized for caller
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
