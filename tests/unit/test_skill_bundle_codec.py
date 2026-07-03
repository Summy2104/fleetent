"""Unit tests for the binary-safe skill bundle codec (skill-git-platform)."""

from __future__ import annotations

from fleetent import skill_bundle_codec


def test_text_round_trips_as_plaintext() -> None:
    text = "# SKILL\n\nhello 世界\n"
    encoded = skill_bundle_codec.encode(text.encode("utf-8"))
    # Text encodes to itself — byte-identical to the pre-codec format (backward compatible).
    assert encoded == text
    assert skill_bundle_codec.is_binary(encoded) is False
    assert skill_bundle_codec.decode(encoded) == text.encode("utf-8")


def test_binary_round_trips_via_base64() -> None:
    # A PNG header — invalid UTF-8, so it must survive as tagged base64.
    blob = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xff\xfe"
    encoded = skill_bundle_codec.encode(blob)
    assert skill_bundle_codec.is_binary(encoded) is True
    assert skill_bundle_codec.decode(encoded) == blob


def test_decode_of_legacy_plaintext_value() -> None:
    # Rows written before the codec stored raw text; decode must still restore their bytes.
    assert skill_bundle_codec.decode("plain legacy content") == b"plain legacy content"
    assert skill_bundle_codec.is_binary("plain legacy content") is False
