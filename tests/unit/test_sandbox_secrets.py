"""Tests for sandbox env name filtering and the three-layer merge pipeline (SB5)."""

from __future__ import annotations

import pytest

from fleetent.integrations.sandbox.secrets import build_sandbox_env, is_sensitive_name


@pytest.mark.parametrize(
    "name",
    [
        "API_TOKEN",
        "token",
        "MyKey",
        "db_secret",
        "DB_PASSWORD",
        "MYSQL_PASSWD",
        "AWS_CREDENTIAL",
        "PRIVATE_PEM",
        "BASIC_AUTH",
        "ANTHROPIC_API_KEY",
    ],
)
def test_is_sensitive_name_true_for_sensitive(name: str) -> None:
    assert is_sensitive_name(name) is True


@pytest.mark.parametrize("name", ["PATH", "HOME", "LANG", "DATA_DIR", "TZ"])
def test_is_sensitive_name_false_for_benign(name: str) -> None:
    assert is_sensitive_name(name) is False


def test_is_sensitive_name_conservative_substring_match() -> None:
    """Conservative取向: 含 KEY 子串的无害名也判敏感 (宁可少注入不可泄漏)。"""
    assert is_sensitive_name("MONKEY") is True
    assert is_sensitive_name("TURKEY") is True


def test_build_sandbox_env_default_excludes_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", "/host")
    result = build_sandbox_env()
    assert "DATA_DIR" not in result


def test_build_sandbox_env_include_host_brings_benign(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", "/host")
    result = build_sandbox_env(include_host=True)
    assert result["DATA_DIR"] == "/host"


def test_build_sandbox_env_include_host_still_filters_sensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-host")
    result = build_sandbox_env(include_host=True)
    assert "ANTHROPIC_API_KEY" not in result


def test_build_sandbox_env_priority_runtime_over_agent_over_host() -> None:
    result = build_sandbox_env(
        host_env={"X": "host"},
        agent_env={"X": "agent"},
        runtime_env={"X": "runtime"},
        include_host=True,
    )
    assert result["X"] == "runtime"


def test_build_sandbox_env_agent_over_host() -> None:
    result = build_sandbox_env(
        host_env={"X": "host"},
        agent_env={"X": "agent"},
        include_host=True,
    )
    assert result["X"] == "agent"


def test_build_sandbox_env_filters_sensitive_from_agent_source() -> None:
    """Agent 显式写入的敏感名也被剔除——合并后单点统一过滤。"""
    result = build_sandbox_env(agent_env={"MY_TOKEN": "x", "DATA_DIR": "/x"})
    assert "MY_TOKEN" not in result
    assert result["DATA_DIR"] == "/x"


def test_build_sandbox_env_filters_sensitive_from_runtime_source() -> None:
    result = build_sandbox_env(runtime_env={"DB_SECRET": "x", "REGION": "eu"})
    assert "DB_SECRET" not in result
    assert result["REGION"] == "eu"


def test_build_sandbox_env_host_anthropic_key_never_leaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3.3: 显式把 ANTHROPIC_API_KEY 写入任一来源, 输出绝不含该键。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-host")
    result = build_sandbox_env(
        agent_env={"ANTHROPIC_API_KEY": "sk-agent"},
        runtime_env={"ANTHROPIC_API_KEY": "sk-runtime"},
        include_host=True,
    )
    assert "ANTHROPIC_API_KEY" not in result
