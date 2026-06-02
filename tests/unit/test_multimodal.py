"""Unit tests for the multimodal content-block helpers (AR21)."""

from __future__ import annotations

import base64

from fleetent.multimodal import (
    build_image_block,
    build_message_with_images,
    has_image_block,
    is_multimodal_content,
    normalize_binary_to_placeholder,
)

# ── is_multimodal_content ──────────────────────────────────────────────────────


def test_is_multimodal_content_true_for_list():
    assert is_multimodal_content([{"type": "text", "text": "hi"}]) is True


def test_is_multimodal_content_false_for_str():
    assert is_multimodal_content("plain text") is False


def test_is_multimodal_content_false_for_none():
    assert is_multimodal_content(None) is False


# ── build_image_block ──────────────────────────────────────────────────────────


def test_build_image_block_shape():
    block = build_image_block(b"\x89PNG\r\n", "image/png")
    assert block["type"] == "image_url"
    assert "image_url" in block
    url = block["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")


def test_build_image_block_roundtrip():
    raw = b"some-fake-image-bytes-\x00\x01\x02"
    block = build_image_block(raw, "image/jpeg")
    b64 = block["image_url"]["url"].split(",", 1)[1]
    assert base64.b64decode(b64) == raw


# ── build_message_with_images ──────────────────────────────────────────────────


def test_build_message_with_text_and_images():
    msg = build_message_with_images(
        "look at these",
        [(b"img1", "image/png"), (b"img2", "image/jpeg")],
    )
    assert msg["role"] == "user"
    content = msg["content"]
    assert isinstance(content, list)
    text_blocks = [b for b in content if b["type"] == "text"]
    image_blocks = [b for b in content if b["type"] == "image_url"]
    assert len(text_blocks) == 1
    assert text_blocks[0]["text"] == "look at these"
    assert len(image_blocks) == 2


def test_build_message_with_images_no_text():
    msg = build_message_with_images("", [(b"img1", "image/png")])
    content = msg["content"]
    assert all(b["type"] == "image_url" for b in content)
    assert len(content) == 1


# ── non-image binary normalization ─────────────────────────────────────────────


def test_non_image_binary_normalized_to_text_placeholder():
    block = normalize_binary_to_placeholder("application/pdf")
    assert block["type"] == "text"
    assert "application/pdf" in block["text"]
    assert "image_url" not in block


def test_build_message_with_images_rejects_non_image_mime():
    # A non-image mime must become a text placeholder, never an image_url block.
    msg = build_message_with_images("hi", [(b"%PDF-1.4", "application/pdf")])
    content = msg["content"]
    assert not any(b["type"] == "image_url" for b in content)
    placeholders = [b for b in content if b["type"] == "text" and "application/pdf" in b["text"]]
    assert len(placeholders) == 1


# ── has_image_block ────────────────────────────────────────────────────────────


def test_has_image_block_true():
    messages = [
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:..."}}]}
    ]
    assert has_image_block(messages) is True


def test_has_image_block_false_for_text_only_array():
    messages = [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]
    assert has_image_block(messages) is False


def test_has_image_block_false_for_str_content():
    messages = [{"role": "user", "content": "hi"}]
    assert has_image_block(messages) is False
