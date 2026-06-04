"""Multimodal input helpers: build and detect image content blocks (AR21).

OpenAI-compatible chat APIs accept a message `content` that is either a plain
string or a list of content blocks, e.g.
`[{"type": "text", "text": ...}, {"type": "image_url", "image_url": {"url": ...}}]`.
This module builds such blocks (images inlined as base64 data URLs so data never
leaves the intranet) and detects image blocks for vision routing. It does not
call any LLM and holds no state.

Audio/video are out of scope; non-image binary attachments are normalized to a
text placeholder rather than passed through as an image block.
"""

from __future__ import annotations

import base64
from typing import Any

_IMAGE_MIME_PREFIX = "image/"

# Fixed placeholder text for unsupported binary attachments (D4).
_UNSUPPORTED_ATTACHMENT_TEXT = "[不支持的附件类型：{mime}]"


def is_multimodal_content(content: Any) -> bool:
    """True when content is a content-block array rather than a plain string."""
    return isinstance(content, list)


def build_image_block(data: bytes, mime: str) -> dict[str, Any]:
    """Build an `image_url` content block with the image inlined as a data URL.

    The bytes are base64-encoded (standard library) and embedded as
    `data:{mime};base64,{b64}` so the image travels inside the message body and
    never leaves the intranet.
    """
    b64 = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def normalize_binary_to_placeholder(mime: str) -> dict[str, Any]:
    """Return a text placeholder block for an unsupported (non-image) attachment."""
    return {"type": "text", "text": _UNSUPPORTED_ATTACHMENT_TEXT.format(mime=mime)}


def build_message_with_images(
    text: str,
    images: list[tuple[bytes, str]],
) -> dict[str, Any]:
    """Assemble a user message with a text block plus one block per attachment.

    Each attachment is `(data, mime)`. Image mimes become `image_url` blocks;
    any other mime becomes a text placeholder (D4 — audio/video/binary are not
    passed through). When `text` is empty, no text block is emitted.
    """
    content: list[dict[str, Any]] = []
    if text:
        content.append({"type": "text", "text": text})
    for data, mime in images:
        if mime.startswith(_IMAGE_MIME_PREFIX):
            content.append(build_image_block(data, mime))
        else:
            content.append(normalize_binary_to_placeholder(mime))
    return {"role": "user", "content": content}


def has_image_block(messages: list[Any]) -> bool:
    """True when any message carries at least one `image_url` content block."""
    for msg in messages:
        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image_url":
                return True
    return False
