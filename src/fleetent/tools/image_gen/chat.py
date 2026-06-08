"""Chat Completions image provider (protocol: openai_image_chat).

Calls /v1/chat/completions and extracts the generated image from the
response content — either as a ``data:image/<ext>;base64,...`` URI or a
bare HTTP URL fallback.
"""

from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

from fleetent.tools.image_gen.provider import ImageGenError, ImageGenProvider, _fetch_url

if TYPE_CHECKING:
    from fleetent.model.resolver import ResolvedModelConfig

from fleetent.tools.image_gen import registry

_DEFAULT_TIMEOUT_SECONDS: float = 120.0
_DATA_URI_RE = re.compile(r"data:image/(\w+);base64,([A-Za-z0-9+/=\s]+)")


def _build_chat_client(base_url: str, api_key: str | None = None) -> AsyncOpenAI:
    return AsyncOpenAI(base_url=base_url, api_key=api_key or "EMPTY")


class ChatImageProvider(ImageGenProvider):
    """Generates images via Chat Completions (openai_image_chat protocol).

    Suitable for models that return images inline in the message content
    (e.g. Gemini image models via NewAPI).
    """

    @property
    def protocol(self) -> str:
        return "openai_image_chat"

    async def generate(
        self,
        resolved: ResolvedModelConfig,
        prompt: str,
        *,
        size: str | None = None,
        api_key: str | None = None,
    ) -> bytes:
        if not resolved.base_url or not resolved.model:
            raise ImageGenError("openai_image_chat requires base_url and model")

        client = _build_chat_client(resolved.base_url, api_key)
        try:
            resp = await client.chat.completions.create(
                model=resolved.model,
                messages=[{"role": "user", "content": prompt}],
                timeout=_DEFAULT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            raise ImageGenError(f"chat completions call failed: {exc}") from exc

        content = resp.choices[0].message.content or "" if resp.choices else ""
        if not content:
            raise ImageGenError("openai_image_chat: empty response from model")

        m = _DATA_URI_RE.search(content)
        if m:
            b64_raw = m.group(2).replace("\n", "").replace(" ", "")
            try:
                return base64.b64decode(b64_raw, validate=True)
            except Exception as exc:
                raise ImageGenError(
                    f"openai_image_chat: invalid base64 in response: {exc}"
                ) from exc

        stripped = content.strip()
        if stripped.startswith("http"):
            return await _fetch_url(stripped)

        raise ImageGenError(
            f"openai_image_chat: no image in response (first 200 chars: {content[:200]!r})"
        )


registry.register(ChatImageProvider())
