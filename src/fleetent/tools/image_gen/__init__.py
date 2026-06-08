"""Pluggable image generation package.

Importing this package registers all built-in providers as a side effect.
Public API: ``generate()`` and ``ImageGenError``.
"""

from __future__ import annotations

from fleetent.agent_config import AgentFile
from fleetent.model.resolver import ModelPolicySnapshot
from fleetent.tools.image_gen import chat as _chat  # noqa: F401 — registers provider
from fleetent.tools.image_gen import openai as _openai  # noqa: F401 — registers provider
from fleetent.tools.image_gen import registry
from fleetent.tools.image_gen.provider import ImageGenError as ImageGenError


async def generate(
    prompt: str,
    *,
    size: str | None = None,
    config: AgentFile | None = None,
) -> bytes:
    """Generate an image and return raw bytes.

    Resolves the ``image_generation`` route from *config* (or the active agent),
    selects the provider matching the route's ``protocol``, and delegates.
    Raises ``ImageGenError`` on any failure.
    """
    from fleetent import agent_config

    src = config or agent_config.active_agent_or_default()
    try:
        policy = ModelPolicySnapshot.from_agent(src)
        resolved = policy.resolve("image_generation")[0]
        api_key = policy.require_api_key(resolved)
    except Exception as exc:
        raise ImageGenError(f"image generation route not configured: {exc}") from exc

    return await registry.dispatch(resolved, prompt, size=size, api_key=api_key)
