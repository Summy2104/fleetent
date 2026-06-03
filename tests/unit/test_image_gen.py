"""Tests for image generation: config constant, client, storage, and tool."""

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent.config import Settings


def test_generated_dir_constant_exists():
    import fleetent.tools as tl

    assert isinstance(tl.GENERATED_DIR, Path)


def test_generated_dir_monkeypatchable(monkeypatch, tmp_path):
    import fleetent.tools as tl

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")
    assert tmp_path / "gen" == tl.GENERATED_DIR


# ── image_gen_client ──────────────────────────────────────────────────────────

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-payload" * 4


def _mock_async_openai(image_obj):
    """Build a mock AsyncOpenAI whose images.generate returns a response."""
    response = SimpleNamespace(data=[image_obj])
    client = MagicMock()
    client.images.generate = AsyncMock(return_value=response)
    return client


def test_generate_decodes_b64_json(monkeypatch):
    import fleetent.image_gen_client as igc

    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    client = _mock_async_openai(SimpleNamespace(b64_json=b64, url=None))
    monkeypatch.setattr(igc, "_build_client", lambda settings: client)

    settings = Settings(anthropic_api_key="k", image_gen_url="http://localhost:9000/v1/")
    result = asyncio_run(igc.generate("a red cube", settings=settings))

    assert result == PNG_BYTES
    # b64_json requested explicitly
    _, kwargs = client.images.generate.call_args
    assert kwargs["response_format"] == "b64_json"
    assert kwargs["prompt"] == "a red cube"


def test_generate_requires_configured_url():
    import fleetent.image_gen_client as igc

    settings = Settings(anthropic_api_key="k", image_gen_url="")
    with pytest.raises(igc.ImageGenError):
        asyncio_run(igc.generate("x", settings=settings))


def test_generate_endpoint_error_raises_imagegenerror(monkeypatch):
    import fleetent.image_gen_client as igc

    client = MagicMock()
    client.images.generate = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(igc, "_build_client", lambda settings: client)

    settings = Settings(anthropic_api_key="k", image_gen_url="http://localhost:9000/v1/")
    with pytest.raises(igc.ImageGenError):
        asyncio_run(igc.generate("x", settings=settings))


def test_generate_empty_data_raises(monkeypatch):
    import fleetent.image_gen_client as igc

    client = MagicMock()
    client.images.generate = AsyncMock(return_value=SimpleNamespace(data=[]))
    monkeypatch.setattr(igc, "_build_client", lambda settings: client)

    settings = Settings(anthropic_api_key="k", image_gen_url="http://localhost:9000/v1/")
    with pytest.raises(igc.ImageGenError):
        asyncio_run(igc.generate("x", settings=settings))


def test_generate_fetches_url_when_no_b64(monkeypatch):
    import fleetent.image_gen_client as igc

    client = _mock_async_openai(
        SimpleNamespace(b64_json=None, url="http://localhost:9000/img/abc.png")
    )
    monkeypatch.setattr(igc, "_build_client", lambda settings: client)

    async def fake_fetch(url: str) -> bytes:
        assert url == "http://localhost:9000/img/abc.png"
        return PNG_BYTES

    monkeypatch.setattr(igc, "_fetch_url", fake_fetch)

    settings = Settings(anthropic_api_key="k", image_gen_url="http://localhost:9000/v1/")
    result = asyncio_run(igc.generate("x", settings=settings))
    assert result == PNG_BYTES


# ── storage helper ────────────────────────────────────────────────────────────


def test_save_image_writes_to_generated_dir(monkeypatch, tmp_path):
    import fleetent.tools as tl

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")
    ref = tl._save_image(PNG_BYTES)

    written = list((tmp_path / "gen").glob("*.png"))
    assert len(written) == 1
    assert written[0].read_bytes() == PNG_BYTES
    # reference points at the file path
    assert str(written[0]) in ref or written[0].name in ref


def test_save_image_uses_uuid_png_name(monkeypatch, tmp_path):
    import fleetent.tools as tl

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")
    tl._save_image(PNG_BYTES)
    name = next((tmp_path / "gen").glob("*.png")).name
    # uuid4 hex (32) + ".png"
    assert name.endswith(".png")
    stem = name[:-4]
    assert len(stem) == 32
    int(stem, 16)  # valid hex


def test_save_image_reference_has_no_base64(monkeypatch, tmp_path):
    import fleetent.tools as tl

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")
    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    ref = tl._save_image(PNG_BYTES)
    assert b64 not in ref


# ── generate_image tool ───────────────────────────────────────────────────────


def test_generate_image_registered_low_risk():
    import fleetent.tools as tl  # noqa: F401 — registers tools
    from fleetent import tool_registry

    assert "generate_image" in tool_registry._registry
    assert tool_registry.get_risk_level("generate_image") == "low"


def test_generate_image_in_schemas():
    import fleetent.tools as tl  # noqa: F401
    from fleetent import tool_registry

    names = [s["function"]["name"] for s in tool_registry.get_schemas()]
    assert "generate_image" in names


def test_generate_image_success_returns_reference(monkeypatch, tmp_path):
    import fleetent.tools as tl

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")

    async def fake_generate(prompt, *, size=None, settings=None):
        assert prompt == "a blue circle"
        return PNG_BYTES

    monkeypatch.setattr(tl.image_gen_client, "generate", fake_generate)

    result = asyncio_run(tl.generate_image(prompt="a blue circle"))

    written = list((tmp_path / "gen").glob("*.png"))
    assert len(written) == 1
    assert written[0].name in result or str(written[0]) in result


def test_generate_image_result_has_no_base64(monkeypatch, tmp_path):
    import fleetent.tools as tl

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")

    async def fake_generate(prompt, *, size=None, settings=None):
        return PNG_BYTES

    monkeypatch.setattr(tl.image_gen_client, "generate", fake_generate)

    result = asyncio_run(tl.generate_image(prompt="x"))
    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    assert b64 not in result


def test_generate_image_failure_normalized_not_raised(monkeypatch, tmp_path):
    import fleetent.tools as tl
    from fleetent.image_gen_client import ImageGenError

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")

    async def fake_generate(prompt, *, size=None, settings=None):
        raise ImageGenError("endpoint not configured")

    monkeypatch.setattr(tl.image_gen_client, "generate", fake_generate)

    result = asyncio_run(tl.generate_image(prompt="x"))
    assert result.startswith("error:")
    assert "endpoint not configured" in result
    # nothing written on failure
    assert not list((tmp_path / "gen").glob("*.png")) if (tmp_path / "gen").exists() else True


# ── trace guard ───────────────────────────────────────────────────────────────


def test_tool_result_message_in_trace_has_no_base64(monkeypatch, tmp_path):
    """A generate_image result fed through eval_logger serialization must not
    leak base64 — the result is a short reference, so this is a regression guard."""
    import json

    import fleetent.tools as tl
    from fleetent import eval_logger

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")

    async def fake_generate(prompt, *, size=None, settings=None):
        return PNG_BYTES

    monkeypatch.setattr(tl.image_gen_client, "generate", fake_generate)
    result = asyncio_run(tl.generate_image(prompt="x"))

    tool_msg = {"role": "tool", "tool_call_id": "call_1", "content": result}
    serialized = eval_logger._serialize(tool_msg)
    blob = json.dumps(serialized, ensure_ascii=False)

    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    assert b64 not in blob


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
