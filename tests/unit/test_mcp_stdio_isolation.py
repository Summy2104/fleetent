"""Unit tests for stdio MCP subprocess environment isolation (mcp-stdio-isolation).

Pure-logic over a monkeypatched os.environ; no real subprocess.
"""

import pytest

import fleetent.integrations.mcp.client as mc


def test_safe_base_env_includes_path(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    assert mc._safe_base_env().get("PATH") == "/usr/bin"


def test_safe_base_env_excludes_platform_secrets(monkeypatch):
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "leak")
    monkeypatch.setenv("DATABASE_URL", "postgres://secret@db/app")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-leak")
    base = mc._safe_base_env()
    assert "SUPER_SECRET_TOKEN" not in base
    assert "DATABASE_URL" not in base
    assert "ANTHROPIC_API_KEY" not in base


def test_subprocess_env_merges_whitelist_and_server_env(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("SECRET_X", "nope")
    server = mc.McpServerConfig(id="s", transport="stdio", env={"FOO": "bar"})
    env = mc._subprocess_env(server)
    assert env["PATH"] == "/usr/bin"
    assert env["FOO"] == "bar"
    assert "SECRET_X" not in env


def test_subprocess_env_server_env_overrides_whitelist(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    server = mc.McpServerConfig(id="s", transport="stdio", env={"PATH": "/custom/bin"})
    assert mc._subprocess_env(server)["PATH"] == "/custom/bin"


def test_subprocess_env_empty_server_env_is_whitelist_only(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("SECRET_Y", "nope")
    server = mc.McpServerConfig(id="s", transport="stdio")
    env = mc._subprocess_env(server)
    assert env.get("PATH") == "/usr/bin"
    assert "SECRET_Y" not in env
    assert "FOO" not in env


# ── register / probe wiring: env passed to StdioServerParameters ─────────────


class _BoomError(Exception):
    pass


def _capture_stdio_params_env(monkeypatch) -> dict:
    """Patch StdioServerParameters to record env then short-circuit before spawning."""
    captured: dict = {}

    def fake_params(command=None, args=None, env=None):
        captured["env"] = env
        raise _BoomError()

    monkeypatch.setattr(mc, "StdioServerParameters", fake_params)
    return captured


async def test_register_stdio_does_not_leak_platform_env(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "leak")
    server = mc.McpServerConfig(id="s", transport="stdio", command="x", env={"FOO": "bar"})
    captured = _capture_stdio_params_env(monkeypatch)
    with pytest.raises(_BoomError):
        await mc._register_session_server(server)
    assert "SUPER_SECRET_TOKEN" not in captured["env"]
    assert captured["env"]["FOO"] == "bar"
    assert captured["env"]["PATH"] == "/usr/bin"


async def test_probe_stdio_does_not_leak_platform_env(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "leak")
    server = mc.McpServerConfig(id="s", transport="stdio", command="x", env={"FOO": "bar"})
    captured = _capture_stdio_params_env(monkeypatch)
    # probe_server swallows the failure into a clean result; the env was still captured.
    result = await mc.probe_server(server)
    assert result["connected"] is False
    assert "SUPER_SECRET_TOKEN" not in captured["env"]
    assert captured["env"]["FOO"] == "bar"
    assert captured["env"]["PATH"] == "/usr/bin"
