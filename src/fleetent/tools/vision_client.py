"""Client for a self-hosted, OpenAI-compatible vision (VLM) endpoint.

Mirrors image_gen_client: an OpenAI-compatible base_url pointed at any
self-hostable VLM behind a compat layer. No cloud-hosted proprietary service —
data stays in-net. Sends a single focused vision chat (instruction text + the
image inlined as a base64 data URL) and returns the model's text answer; the
calling tool reads images from disk by reference, so base64 never enters the
main context or trace.
"""

import base64
from typing import Any

from openai import AsyncOpenAI

from fleetent.agent_config import AgentFile
from fleetent.model import ModelConfigError, ModelPolicySnapshot

# VLMs answer in seconds; generous but bounded so a hung endpoint fails locally.
_DEFAULT_TIMEOUT_SECONDS: float = 120.0

# Inlining as a data URL keeps the image inside the request body (in-net),
# matching multimodal.build_image_block.
_DATA_URL_MIME = "image/png"


class VisionError(Exception):
    """Raised when image analysis cannot produce text (unconfigured endpoint,
    endpoint error/timeout, or an unusable response)."""


def _build_client(base_url: str, api_key: str | None = None) -> AsyncOpenAI:
    """Build an AsyncOpenAI bound to the configured vision endpoint.

    Self-hosted endpoints often ignore the key; a non-empty placeholder keeps
    the SDK from rejecting the request before it reaches the backend.
    """
    return AsyncOpenAI(base_url=base_url, api_key=api_key or "vision")


async def analyze(
    image_bytes: bytes,
    instruction: str,
    *,
    config: AgentFile | None = None,
) -> str:
    """Run one focused vision call over the image and return the text answer.

    Sends a standard OpenAI-compatible vision message (an instruction text block
    plus an `image_url` block carrying the image as a base64 data URL) and
    returns the assistant text. Any failure is raised as VisionError for the
    caller to normalize into a tool-result error string.
    """
    from fleetent import agent_config

    src = config or agent_config.active_agent_or_default()
    try:
        policy = ModelPolicySnapshot.from_agent(src)
        resolved = policy.resolve("vision")[0]
        if resolved.protocol != "openai_chat" or not resolved.base_url or not resolved.model:
            raise ModelConfigError("vision route must target an openai_chat model")
        api_key = policy.require_api_key(resolved)
    except Exception as exc:
        raise VisionError(f"vision route not configured: {exc}") from exc

    client = _build_client(resolved.base_url, api_key)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    content: list[Any] = [
        {"type": "text", "text": instruction},
        {"type": "image_url", "image_url": {"url": f"data:{_DATA_URL_MIME};base64,{b64}"}},
    ]
    messages: list[Any] = [{"role": "user", "content": content}]
    try:
        response = await client.chat.completions.create(
            model=resolved.model,
            messages=messages,
            timeout=_DEFAULT_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # endpoint error / timeout — normalized for caller
        raise VisionError(f"vision endpoint call failed: {exc}") from exc

    choices = getattr(response, "choices", None)
    if not choices:
        raise VisionError("vision endpoint returned no choices")
    text = getattr(choices[0].message, "content", None)
    if not text:
        raise VisionError("vision endpoint returned empty content")
    return str(text)
