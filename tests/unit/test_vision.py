"""Tests for vision-as-tool: VLM client, uploads storage, and analyze_image."""

import asyncio
import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent.agent_config import AgentFile, default_models

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-payload" * 4


def asyncio_run(coro):
    return asyncio.run(coro)


# ── config ─────────────────────────────────────────────────────────────────────


def test_vision_config_defaults():
    settings = AgentFile(name="t", version=1, models=default_models())
    assert settings.models.routes["vision"][0].target == "vision"


def _vision_agent() -> AgentFile:
    return AgentFile.model_validate(
        {
            "name": "t",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "vision",
                        "provider": "local",
                        "protocol": "openai_chat",
                        "base_url": "http://localhost:9001/v1/",
                        "model": "qwen-vl",
                    }
                ],
                "routes": {"vision": [{"target": "vision"}]},
            },
        }
    )


def _no_vision_agent() -> AgentFile:
    return AgentFile.model_validate(
        {
            "name": "t",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "primary",
                        "provider": "local",
                        "protocol": "openai_chat",
                        "base_url": "http://localhost:9001/v1/",
                        "model": "text",
                    }
                ],
                "routes": {"default": [{"target": "primary"}]},
            },
        }
    )


# ── vision_client ────────────────────────────────────────────────────────────


def _mock_async_openai(text: str):
    """Build a mock AsyncOpenAI whose chat.completions.create returns text."""
    message = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=message)
    response = SimpleNamespace(choices=[choice])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


def test_analyze_sends_image_and_instruction_returns_text(monkeypatch):
    import fleetent.tools.vision_client as vc

    client = _mock_async_openai("an invoice for $42")
    monkeypatch.setattr(vc, "_build_client", lambda *args, **kwargs: client)

    result = asyncio_run(vc.analyze(PNG_BYTES, "what is this?", config=_vision_agent()))

    assert result == "an invoice for $42"
    _, kwargs = client.chat.completions.create.call_args
    # The request carries a content-block array with the instruction text and an
    # image_url block (base64 data URL) — standard OpenAI-compatible vision shape.
    messages = kwargs["messages"]
    content = messages[0]["content"]
    types = [b["type"] for b in content]
    assert "text" in types
    assert "image_url" in types
    text_block = next(b for b in content if b["type"] == "text")
    assert "what is this?" in text_block["text"]
    image_block = next(b for b in content if b["type"] == "image_url")
    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    assert b64 in image_block["image_url"]["url"]
    assert kwargs["model"] == "qwen-vl"


def test_analyze_requires_configured_url():
    import fleetent.tools.vision_client as vc

    with pytest.raises(vc.VisionError):
        asyncio_run(vc.analyze(PNG_BYTES, "x", config=_no_vision_agent()))


def test_analyze_endpoint_error_raises_visionerror(monkeypatch):
    import fleetent.tools.vision_client as vc

    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(vc, "_build_client", lambda *args, **kwargs: client)

    with pytest.raises(vc.VisionError):
        asyncio_run(vc.analyze(PNG_BYTES, "x", config=_vision_agent()))


def test_analyze_empty_choices_raises(monkeypatch):
    import fleetent.tools.vision_client as vc

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=SimpleNamespace(choices=[]))
    monkeypatch.setattr(vc, "_build_client", lambda *args, **kwargs: client)

    with pytest.raises(vc.VisionError):
        asyncio_run(vc.analyze(PNG_BYTES, "x", config=_vision_agent()))


# ── uploads storage helper ──────────────────────────────────────────────────


def test_uploads_dir_constant_exists():
    import fleetent.tools.builtin_tools as tl

    assert isinstance(tl.UPLOADS_DIR, Path)


def test_uploads_dir_monkeypatchable(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")
    assert tmp_path / "up" == tl.UPLOADS_DIR


def test_save_upload_writes_and_reads_back(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")
    ref = tl._save_upload(PNG_BYTES, "image/png")

    written = list((tmp_path / "up").glob("*"))
    assert len(written) == 1
    assert written[0].read_bytes() == PNG_BYTES
    # reference is a path string, no base64
    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    assert b64 not in ref
    # the reference reads back to the original bytes
    assert tl._read_upload(ref) == PNG_BYTES


def test_save_upload_reference_is_path(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")
    ref = tl._save_upload(PNG_BYTES, "image/jpeg")
    assert ref.endswith(".jpeg") or ref.endswith(".jpg") or Path(ref).suffix
    assert str(tmp_path / "up") in ref


# ── analyze_image tool ──────────────────────────────────────────────────────


def test_analyze_image_registered():
    import fleetent.tools.builtin_tools as tl  # noqa: F401 — registers tools
    from fleetent.tools import registry as tool_registry

    assert "analyze_image" in tool_registry._registry
    names = [s["function"]["name"] for s in tool_registry.get_schemas()]
    assert "analyze_image" in names


def test_analyze_image_valid_ref_returns_text(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")
    ref = tl._save_upload(PNG_BYTES, "image/png")

    async def fake_analyze(image_bytes, instruction, *, config=None):
        assert image_bytes == PNG_BYTES
        assert instruction == "read the total"
        return "total is $42"

    monkeypatch.setattr(tl.vision_client, "analyze", fake_analyze)

    result = asyncio_run(tl.analyze_image(ref=ref, instruction="read the total"))
    assert "total is $42" in result


def test_analyze_image_result_has_no_base64(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")
    ref = tl._save_upload(PNG_BYTES, "image/png")

    async def fake_analyze(image_bytes, instruction, *, config=None):
        return "described"

    monkeypatch.setattr(tl.vision_client, "analyze", fake_analyze)

    result = asyncio_run(tl.analyze_image(ref=ref, instruction="x"))
    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    assert b64 not in result


def test_analyze_image_invalid_ref_returns_error_not_raised(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")
    result = asyncio_run(
        tl.analyze_image(ref=str(tmp_path / "up" / "missing.png"), instruction="x")
    )
    assert result.startswith("error:")


def test_analyze_image_unconfigured_endpoint_returns_error(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl
    from fleetent.tools.vision_client import VisionError

    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")
    ref = tl._save_upload(PNG_BYTES, "image/png")

    async def fake_analyze(image_bytes, instruction, *, config=None):
        raise VisionError("vision endpoint not configured (vision_url is empty)")

    monkeypatch.setattr(tl.vision_client, "analyze", fake_analyze)

    result = asyncio_run(tl.analyze_image(ref=ref, instruction="x"))
    assert result.startswith("error:")
    assert "not configured" in result


# ── trace guard ──────────────────────────────────────────────────────────────


def test_analyze_image_result_in_trace_has_no_base64(monkeypatch, tmp_path):
    import json

    import fleetent.tools.builtin_tools as tl
    from fleetent import eval_logger

    monkeypatch.setattr(tl, "UPLOADS_DIR", tmp_path / "up")
    ref = tl._save_upload(PNG_BYTES, "image/png")

    async def fake_analyze(image_bytes, instruction, *, config=None):
        return "structured description"

    monkeypatch.setattr(tl.vision_client, "analyze", fake_analyze)
    result = asyncio_run(tl.analyze_image(ref=ref, instruction="x"))

    tool_msg = {"role": "tool", "tool_call_id": "call_1", "content": result}
    serialized = eval_logger._serialize(tool_msg)
    blob = json.dumps(serialized, ensure_ascii=False)

    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    assert b64 not in blob
