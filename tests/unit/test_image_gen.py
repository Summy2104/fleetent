"""Tests for image generation: config constant, client, storage, and tool."""

import base64
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent.agent_config import AgentFile


def test_generated_dir_constant_exists():
    import fleetent.tools.builtin_tools as tl

    assert isinstance(tl.GENERATED_DIR, Path)


def test_generated_dir_monkeypatchable(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

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


def _image_agent() -> AgentFile:
    return AgentFile.model_validate(
        {
            "name": "image-agent",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "image",
                        "provider": "local",
                        "protocol": "openai_image_generation",
                        "endpoint": "http://image.local/v1/images/generations",
                        "model": "flux",
                    }
                ],
                "routes": {"image_generation": [{"target": "image"}]},
            },
        }
    )


def test_generate_decodes_b64_json(monkeypatch):
    from fleetent.tools.image_gen import openai as openai_provider

    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    client = _mock_async_openai(SimpleNamespace(b64_json=b64, url=None))
    monkeypatch.setattr(openai_provider, "_build_client", lambda *args, **kwargs: client)

    import fleetent.tools.image_gen_client as igc

    result = asyncio_run(igc.generate("a red cube", config=_image_agent()))

    assert result == PNG_BYTES
    _, kwargs = client.images.generate.call_args
    assert kwargs["response_format"] == "b64_json"
    assert kwargs["prompt"] == "a red cube"


def test_generate_uses_image_generation_route(monkeypatch):
    from fleetent.tools.image_gen import openai as openai_provider

    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    client = _mock_async_openai(SimpleNamespace(b64_json=b64, url=None))
    built: list[tuple[str, str | None]] = []

    def build_client(endpoint: str, api_key: str | None = None):
        built.append((endpoint, api_key))
        return client

    monkeypatch.setattr(openai_provider, "_build_client", build_client)

    import fleetent.tools.image_gen_client as igc

    result = asyncio_run(igc.generate("a red cube", config=_image_agent()))

    assert result == PNG_BYTES
    assert built == [("http://image.local/v1/images/generations", None)]
    _, kwargs = client.images.generate.call_args
    assert kwargs["model"] == "flux"


def test_generate_requires_configured_url():
    import fleetent.tools.image_gen_client as igc

    settings = AgentFile.model_validate(
        {
            "name": "t",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "primary",
                        "provider": "local",
                        "protocol": "openai_chat",
                        "base_url": "http://local.test/v1/",
                        "model": "text",
                    }
                ],
                "routes": {"default": [{"target": "primary"}]},
            },
        }
    )
    with pytest.raises(igc.ImageGenError):
        asyncio_run(igc.generate("x", config=settings))


def test_generate_endpoint_error_raises_imagegenerror(monkeypatch):
    from fleetent.tools.image_gen import openai as openai_provider

    client = MagicMock()
    client.images.generate = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(openai_provider, "_build_client", lambda *args, **kwargs: client)

    import fleetent.tools.image_gen_client as igc

    with pytest.raises(igc.ImageGenError):
        asyncio_run(igc.generate("x", config=_image_agent()))


def test_generate_empty_data_raises(monkeypatch):
    from fleetent.tools.image_gen import openai as openai_provider

    client = MagicMock()
    client.images.generate = AsyncMock(return_value=SimpleNamespace(data=[]))
    monkeypatch.setattr(openai_provider, "_build_client", lambda *args, **kwargs: client)

    import fleetent.tools.image_gen_client as igc

    with pytest.raises(igc.ImageGenError):
        asyncio_run(igc.generate("x", config=_image_agent()))


def test_generate_fetches_url_when_no_b64(monkeypatch):
    from fleetent.tools.image_gen import openai as openai_provider

    client = _mock_async_openai(
        SimpleNamespace(b64_json=None, url="http://localhost:9000/img/abc.png")
    )
    monkeypatch.setattr(openai_provider, "_build_client", lambda *args, **kwargs: client)

    async def fake_fetch(url: str) -> bytes:
        assert url == "http://localhost:9000/img/abc.png"
        return PNG_BYTES

    monkeypatch.setattr(openai_provider, "_fetch_url", fake_fetch)

    import fleetent.tools.image_gen_client as igc

    result = asyncio_run(igc.generate("x", config=_image_agent()))
    assert result == PNG_BYTES


# ── storage helper ────────────────────────────────────────────────────────────


def test_save_image_writes_to_generated_dir(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")
    ref = tl._save_image(PNG_BYTES)

    written = list((tmp_path / "gen").glob("*.png"))
    assert len(written) == 1
    assert written[0].read_bytes() == PNG_BYTES
    # reference points at the file path
    assert str(written[0]) in ref or written[0].name in ref


def test_save_image_uses_uuid_png_name(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")
    tl._save_image(PNG_BYTES)
    name = next((tmp_path / "gen").glob("*.png")).name
    # uuid4 hex (32) + ".png"
    assert name.endswith(".png")
    stem = name[:-4]
    assert len(stem) == 32
    int(stem, 16)  # valid hex


def test_save_image_reference_has_no_base64(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")
    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    ref = tl._save_image(PNG_BYTES)
    assert b64 not in ref


# ── generate_image tool ───────────────────────────────────────────────────────


def test_generate_image_registered_low_risk():
    import fleetent.tools.builtin_tools as tl  # noqa: F401 — registers tools
    from fleetent.tools import registry as tool_registry

    assert "generate_image" in tool_registry._registry
    assert tool_registry.get_risk_level("generate_image") == "low"


def test_generate_image_in_schemas():
    import fleetent.tools.builtin_tools as tl  # noqa: F401
    from fleetent.tools import registry as tool_registry

    names = [s["function"]["name"] for s in tool_registry.get_schemas()]
    assert "generate_image" in names


def test_generate_image_success_returns_reference(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")

    async def fake_generate(prompt, *, size=None, config=None):
        assert prompt == "a blue circle"
        return PNG_BYTES

    monkeypatch.setattr(tl.image_gen_client, "generate", fake_generate)

    result = asyncio_run(tl.generate_image(prompt="a blue circle"))

    written = list((tmp_path / "gen").glob("*.png"))
    assert len(written) == 1
    assert written[0].name in result or str(written[0]) in result


def test_generate_image_result_has_no_base64(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")

    async def fake_generate(prompt, *, size=None, config=None):
        return PNG_BYTES

    monkeypatch.setattr(tl.image_gen_client, "generate", fake_generate)

    result = asyncio_run(tl.generate_image(prompt="x"))
    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    assert b64 not in result


def test_generate_image_failure_normalized_not_raised(monkeypatch, tmp_path):
    import fleetent.tools.builtin_tools as tl
    from fleetent.tools.image_gen_client import ImageGenError

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")

    async def fake_generate(prompt, *, size=None, config=None):
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

    import fleetent.tools.builtin_tools as tl
    from fleetent import eval_logger

    monkeypatch.setattr(tl, "GENERATED_DIR", tmp_path / "gen")

    async def fake_generate(prompt, *, size=None, config=None):
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


# ── provider ABC ──────────────────────────────────────────────────────────────


def test_image_gen_error_is_exception_subclass():
    from fleetent.tools.image_gen.provider import ImageGenError

    assert issubclass(ImageGenError, Exception)
    err = ImageGenError("boom")
    assert str(err) == "boom"


def test_image_gen_provider_abc_not_instantiable():
    from fleetent.tools.image_gen.provider import ImageGenProvider

    with pytest.raises(TypeError):
        ImageGenProvider()  # type: ignore[abstract]


def test_fetch_url_raises_image_gen_error_on_non_200(monkeypatch):
    import httpx

    from fleetent.tools.image_gen.provider import ImageGenError, _fetch_url

    async def fake_get(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )
        return mock_resp

    monkeypatch.setattr("httpx.AsyncClient.get", fake_get)
    with pytest.raises(ImageGenError):
        asyncio_run(_fetch_url("http://localhost:9000/img/fail.png"))


# ── registry ──────────────────────────────────────────────────────────────────


def test_registry_register_and_dispatch_by_protocol(monkeypatch):
    import fleetent.tools.image_gen.registry as reg
    from fleetent.tools.image_gen.provider import ImageGenProvider

    # Fresh registry for isolation
    monkeypatch.setattr(reg, "_PROVIDERS", {})

    class FakeProvider(ImageGenProvider):
        @property
        def protocol(self) -> str:
            return "test_proto"

        async def generate(self, resolved, prompt, *, size=None, api_key=None) -> bytes:
            return b"fake-bytes"

    reg.register(FakeProvider())

    from types import SimpleNamespace

    fake_resolved = SimpleNamespace(protocol="test_proto")
    result = asyncio_run(reg.dispatch(fake_resolved, "a cat"))
    assert result == b"fake-bytes"


def test_registry_dispatch_unknown_protocol_raises(monkeypatch):
    import fleetent.tools.image_gen.registry as reg
    from fleetent.tools.image_gen.provider import ImageGenError

    monkeypatch.setattr(reg, "_PROVIDERS", {})

    from types import SimpleNamespace

    fake_resolved = SimpleNamespace(protocol="no_such_proto")
    with pytest.raises(ImageGenError, match="no_such_proto"):
        asyncio_run(reg.dispatch(fake_resolved, "a dog"))


# ── OpenAIImagesProvider ──────────────────────────────────────────────────────


def _openai_image_agent() -> AgentFile:
    return AgentFile.model_validate(
        {
            "name": "image-agent",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "image",
                        "provider": "local",
                        "protocol": "openai_image_generation",
                        "endpoint": "http://image.local/v1/images/generations",
                        "model": "flux",
                    }
                ],
                "routes": {"image_generation": [{"target": "image"}]},
            },
        }
    )


def _mock_openai_images_client(image_obj):
    response = SimpleNamespace(data=[image_obj])
    client = MagicMock()
    client.images.generate = AsyncMock(return_value=response)
    return client


def test_openai_provider_decodes_b64_json(monkeypatch):
    from fleetent.tools.image_gen import openai as openai_provider

    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    client = _mock_openai_images_client(SimpleNamespace(b64_json=b64, url=None))
    monkeypatch.setattr(openai_provider, "_build_client", lambda *a, **kw: client)

    from fleetent.tools.image_gen.openai import OpenAIImagesProvider
    from fleetent.model.resolver import ModelPolicySnapshot

    provider = OpenAIImagesProvider()
    policy = ModelPolicySnapshot.from_agent(_openai_image_agent())
    resolved = policy.resolve("image_generation")[0]
    result = asyncio_run(provider.generate(resolved, "a red cube", api_key=None))
    assert result == PNG_BYTES
    _, kwargs = client.images.generate.call_args
    assert kwargs["response_format"] == "b64_json"


def test_openai_provider_uses_endpoint_and_model(monkeypatch):
    from fleetent.tools.image_gen import openai as openai_provider

    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    client = _mock_openai_images_client(SimpleNamespace(b64_json=b64, url=None))
    built: list[tuple[str, str | None]] = []

    def fake_build(endpoint, api_key=None):
        built.append((endpoint, api_key))
        return client

    monkeypatch.setattr(openai_provider, "_build_client", fake_build)

    from fleetent.tools.image_gen.openai import OpenAIImagesProvider
    from fleetent.model.resolver import ModelPolicySnapshot

    provider = OpenAIImagesProvider()
    policy = ModelPolicySnapshot.from_agent(_openai_image_agent())
    resolved = policy.resolve("image_generation")[0]
    asyncio_run(provider.generate(resolved, "a cube", api_key=None))

    assert built == [("http://image.local/v1/images/generations", None)]
    _, kwargs = client.images.generate.call_args
    assert kwargs["model"] == "flux"


def test_openai_provider_endpoint_error_raises(monkeypatch):
    from fleetent.tools.image_gen import openai as openai_provider
    from fleetent.tools.image_gen.provider import ImageGenError

    client = MagicMock()
    client.images.generate = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(openai_provider, "_build_client", lambda *a, **kw: client)

    from fleetent.tools.image_gen.openai import OpenAIImagesProvider
    from fleetent.model.resolver import ModelPolicySnapshot

    provider = OpenAIImagesProvider()
    policy = ModelPolicySnapshot.from_agent(_openai_image_agent())
    resolved = policy.resolve("image_generation")[0]
    with pytest.raises(ImageGenError):
        asyncio_run(provider.generate(resolved, "x", api_key=None))


def test_openai_provider_empty_data_raises(monkeypatch):
    from fleetent.tools.image_gen import openai as openai_provider
    from fleetent.tools.image_gen.provider import ImageGenError

    client = MagicMock()
    client.images.generate = AsyncMock(return_value=SimpleNamespace(data=[]))
    monkeypatch.setattr(openai_provider, "_build_client", lambda *a, **kw: client)

    from fleetent.tools.image_gen.openai import OpenAIImagesProvider
    from fleetent.model.resolver import ModelPolicySnapshot

    provider = OpenAIImagesProvider()
    policy = ModelPolicySnapshot.from_agent(_openai_image_agent())
    resolved = policy.resolve("image_generation")[0]
    with pytest.raises(ImageGenError):
        asyncio_run(provider.generate(resolved, "x", api_key=None))


def test_openai_provider_fetches_url_when_no_b64(monkeypatch):
    from fleetent.tools.image_gen import openai as openai_provider

    client = _mock_openai_images_client(
        SimpleNamespace(b64_json=None, url="http://localhost:9000/img/abc.png")
    )
    monkeypatch.setattr(openai_provider, "_build_client", lambda *a, **kw: client)

    async def fake_fetch(url: str) -> bytes:
        assert url == "http://localhost:9000/img/abc.png"
        return PNG_BYTES

    monkeypatch.setattr(openai_provider, "_fetch_url", fake_fetch)

    from fleetent.tools.image_gen.openai import OpenAIImagesProvider
    from fleetent.model.resolver import ModelPolicySnapshot

    provider = OpenAIImagesProvider()
    policy = ModelPolicySnapshot.from_agent(_openai_image_agent())
    resolved = policy.resolve("image_generation")[0]
    result = asyncio_run(provider.generate(resolved, "x", api_key=None))
    assert result == PNG_BYTES


# ── ChatImageProvider ─────────────────────────────────────────────────────────

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"fake-jpeg-payload" * 4


def _chat_agent(model: str = "gemini-3-pro-image-preview") -> AgentFile:
    return AgentFile.model_validate(
        {
            "name": "chat-image-agent",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "img",
                        "provider": "newapi",
                        "protocol": "openai_image_chat",
                        "base_url": "http://newapi.local/v1",
                        "model": model,
                    }
                ],
                "routes": {"image_generation": [{"target": "img"}]},
            },
        }
    )


def _mock_chat_client(content: str):
    msg = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=msg)
    resp = SimpleNamespace(choices=[choice])
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=resp)
    return client


def test_chat_provider_extracts_data_uri_jpeg(monkeypatch):
    from fleetent.tools.image_gen import chat as chat_mod

    b64 = base64.b64encode(JPEG_BYTES).decode("ascii")
    content = f"Here is your image: data:image/jpeg;base64,{b64}"
    client = _mock_chat_client(content)
    monkeypatch.setattr(chat_mod, "_build_chat_client", lambda *a, **kw: client)

    from fleetent.tools.image_gen.chat import ChatImageProvider
    from fleetent.model.resolver import ModelPolicySnapshot

    provider = ChatImageProvider()
    policy = ModelPolicySnapshot.from_agent(_chat_agent())
    resolved = policy.resolve("image_generation")[0]
    result = asyncio_run(provider.generate(resolved, "a cat", api_key=None))
    assert result == JPEG_BYTES


def test_chat_provider_extracts_data_uri_png(monkeypatch):
    from fleetent.tools.image_gen import chat as chat_mod

    b64 = base64.b64encode(PNG_BYTES).decode("ascii")
    content = f"![image](data:image/png;base64,{b64})"
    client = _mock_chat_client(content)
    monkeypatch.setattr(chat_mod, "_build_chat_client", lambda *a, **kw: client)

    from fleetent.tools.image_gen.chat import ChatImageProvider
    from fleetent.model.resolver import ModelPolicySnapshot

    provider = ChatImageProvider()
    policy = ModelPolicySnapshot.from_agent(_chat_agent())
    resolved = policy.resolve("image_generation")[0]
    result = asyncio_run(provider.generate(resolved, "a dog", api_key=None))
    assert result == PNG_BYTES


def test_chat_provider_fetches_bare_url_fallback(monkeypatch):
    from fleetent.tools.image_gen import chat as chat_mod

    content = "http://localhost:9000/img/generated.png"
    client = _mock_chat_client(content)
    monkeypatch.setattr(chat_mod, "_build_chat_client", lambda *a, **kw: client)

    async def fake_fetch(url: str) -> bytes:
        assert url == "http://localhost:9000/img/generated.png"
        return PNG_BYTES

    monkeypatch.setattr(chat_mod, "_fetch_url", fake_fetch)

    from fleetent.tools.image_gen.chat import ChatImageProvider
    from fleetent.model.resolver import ModelPolicySnapshot

    provider = ChatImageProvider()
    policy = ModelPolicySnapshot.from_agent(_chat_agent())
    resolved = policy.resolve("image_generation")[0]
    result = asyncio_run(provider.generate(resolved, "x", api_key=None))
    assert result == PNG_BYTES


def test_chat_provider_empty_response_raises(monkeypatch):
    from fleetent.tools.image_gen import chat as chat_mod
    from fleetent.tools.image_gen.provider import ImageGenError

    client = _mock_chat_client("")
    monkeypatch.setattr(chat_mod, "_build_chat_client", lambda *a, **kw: client)

    from fleetent.tools.image_gen.chat import ChatImageProvider
    from fleetent.model.resolver import ModelPolicySnapshot

    provider = ChatImageProvider()
    policy = ModelPolicySnapshot.from_agent(_chat_agent())
    resolved = policy.resolve("image_generation")[0]
    with pytest.raises(ImageGenError):
        asyncio_run(provider.generate(resolved, "x", api_key=None))


def test_chat_provider_no_image_in_text_raises(monkeypatch):
    from fleetent.tools.image_gen import chat as chat_mod
    from fleetent.tools.image_gen.provider import ImageGenError

    client = _mock_chat_client("Sorry, I cannot generate images.")
    monkeypatch.setattr(chat_mod, "_build_chat_client", lambda *a, **kw: client)

    from fleetent.tools.image_gen.chat import ChatImageProvider
    from fleetent.model.resolver import ModelPolicySnapshot

    provider = ChatImageProvider()
    policy = ModelPolicySnapshot.from_agent(_chat_agent())
    resolved = policy.resolve("image_generation")[0]
    with pytest.raises(ImageGenError, match="no image"):
        asyncio_run(provider.generate(resolved, "x", api_key=None))


# ── image_gen/__init__ dispatch ───────────────────────────────────────────────


def test_image_gen_generate_dispatches_to_provider(monkeypatch):
    import fleetent.tools.image_gen.registry as reg
    from fleetent.tools.image_gen.provider import ImageGenProvider

    monkeypatch.setattr(reg, "_PROVIDERS", {})

    class FakeProvider(ImageGenProvider):
        @property
        def protocol(self) -> str:
            return "openai_image_generation"

        async def generate(self, resolved, prompt, *, size=None, api_key=None) -> bytes:
            return PNG_BYTES

    reg.register(FakeProvider())

    import fleetent.tools.image_gen as ig

    result = asyncio_run(ig.generate("a cube", config=_openai_image_agent()))
    assert result == PNG_BYTES


# ── shim backward compat ──────────────────────────────────────────────────────


def test_shim_generate_is_same_object():
    import fleetent.tools.image_gen as ig
    import fleetent.tools.image_gen_client as shim

    assert shim.generate is ig.generate


def test_shim_image_gen_error_is_same_class():
    import fleetent.tools.image_gen.provider as prov
    import fleetent.tools.image_gen_client as shim

    assert shim.ImageGenError is prov.ImageGenError


# ── agent_config: openai_image_chat validation ────────────────────────────────


def test_openai_image_chat_valid_passes():
    AgentFile.model_validate(
        {
            "name": "t",
            "version": 1,
            "models": {
                "targets": [
                    {
                        "id": "img",
                        "provider": "newapi",
                        "protocol": "openai_image_chat",
                        "base_url": "http://newapi.local/v1",
                        "model": "gemini-3-pro-image-preview",
                    }
                ],
                "routes": {"image_generation": [{"target": "img"}]},
            },
        }
    )


def test_openai_image_chat_missing_base_url_raises():
    with pytest.raises(Exception):
        AgentFile.model_validate(
            {
                "name": "t",
                "version": 1,
                "models": {
                    "targets": [
                        {
                            "id": "img",
                            "provider": "newapi",
                            "protocol": "openai_image_chat",
                            "model": "gemini-3-pro-image-preview",
                        }
                    ],
                    "routes": {"image_generation": [{"target": "img"}]},
                },
            }
        )


def test_openai_image_chat_missing_model_raises():
    with pytest.raises(Exception):
        AgentFile.model_validate(
            {
                "name": "t",
                "version": 1,
                "models": {
                    "targets": [
                        {
                            "id": "img",
                            "provider": "newapi",
                            "protocol": "openai_image_chat",
                            "base_url": "http://newapi.local/v1",
                        }
                    ],
                    "routes": {"image_generation": [{"target": "img"}]},
                },
            }
        )

