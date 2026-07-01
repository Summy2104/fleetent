"""Unit tests: 聊天 LLM client 显式超时与有界重试（harden-im-llm-timeout-handling P2）。"""

from __future__ import annotations

import httpx

import fleetent.runtime.loop as loop
from fleetent.model.resolver import ResolvedModelConfig


def _resolved() -> ResolvedModelConfig:
    return ResolvedModelConfig(
        agent_name="a",
        route_key="default",
        target_id="primary",
        provider="openai_compatible",
        protocol="openai_chat",
        base_url="https://example.test/v1/",
        model="m",
        api_key_env="LLM_API_KEY",
    )


def test_client_has_explicit_finite_read_timeout() -> None:
    client = loop._build_async_client(_resolved(), "k")
    timeout = client.timeout
    assert isinstance(timeout, httpx.Timeout)
    # read 必须是有限值（非 None、非默认无界），使流式 chunk 间停顿有边界
    assert timeout.read is not None
    assert timeout.read < 600  # 不依赖 SDK 默认 600s


def test_client_has_bounded_max_retries() -> None:
    client = loop._build_async_client(_resolved(), "k")
    assert client.max_retries > 0
    assert client.max_retries < 10  # 有界


def test_timeout_threshold_is_injectable() -> None:
    # 阈值来自模块内常量，便于 monkeypatch 测试覆盖
    assert hasattr(loop, "_LLM_TIMEOUT")
    assert isinstance(loop._LLM_TIMEOUT, httpx.Timeout)
    assert hasattr(loop, "_LLM_MAX_RETRIES")
    assert isinstance(loop._LLM_MAX_RETRIES, int)


def test_client_respects_monkeypatched_constants(monkeypatch) -> None:
    patched = httpx.Timeout(connect=1.0, read=7.0, write=2.0, pool=1.0)
    monkeypatch.setattr(loop, "_LLM_TIMEOUT", patched)
    monkeypatch.setattr(loop, "_LLM_MAX_RETRIES", 4)
    client = loop._build_async_client(_resolved(), "k")
    assert client.timeout.read == 7.0
    assert client.max_retries == 4
