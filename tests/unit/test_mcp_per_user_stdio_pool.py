"""Unit tests for Group 5: stdio per-user subprocess pool + lifecycle.

Covers the stdio per-user OAuth path: per-(scope, server, user) subprocess keying and
reuse, the user's access token injected into the subprocess env at spawn, owner-task
lifecycle (enter/exit same task, reaping via close-signal — never cross-task unwinding),
token-expiry/401 restart, idle reaping, total + per-user caps with eviction logging, the
orphan-cleanup hook, and bulkheaded shutdown. The SDK transport / ClientSession and the
per-user token resolver are stubbed — no real subprocess, wire, DB, or FastAPI.
"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from typing import Any

import pytest

import fleetent.integrations.mcp.client as mc
from fleetent.integrations.mcp.client import McpServerConfig
from fleetent.integrations.mcp.per_user_tokens import UserToken

# ── server fixtures ────────────────────────────────────────────────────────────


def _per_user_stdio_server(sid: str = "puo", token_env: str = "") -> McpServerConfig:
    return McpServerConfig(
        id=sid,
        transport="stdio",
        command="python",
        args=["-m", "server"],
        auth_type="oauth2",
        oauth_grant="authorization_code",
        token_env=token_env,
    )


def _plain_stdio_server(sid: str = "plain") -> McpServerConfig:
    return McpServerConfig(id=sid, transport="stdio", command="python", args=["-m", "server"])


def _tool(name: str, desc: str = "d") -> SimpleNamespace:
    return SimpleNamespace(
        name=name, description=desc, inputSchema={"type": "object", "properties": {}}
    )


class _StubSession:
    """Records call_tool invocations; raise_on_call lets a test simulate a 401."""

    def __init__(self, *, tools: list[Any] | None = None, raise_on_call: Exception | None = None):
        self._tools = tools or []
        self._raise_on_call = raise_on_call
        self.calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def initialize(self) -> Any:
        return SimpleNamespace(protocolVersion="1", capabilities={})

    async def list_tools(self, cursor: str | None = None) -> Any:
        return SimpleNamespace(tools=self._tools, nextCursor=None)

    async def call_tool(self, name: str, args: dict) -> Any:
        self.calls.append((name, args))
        if self._raise_on_call is not None:
            raise self._raise_on_call
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            structuredContent=None,
            isError=False,
        )


class _StubTransportCM:
    """Records enter/exit task identity + the spawn env for the cancel-scope probe."""

    def __init__(self, rec: dict, env: dict[str, str]):
        self._rec = rec
        self._env = env

    async def __aenter__(self):
        self._rec.setdefault("enter_tasks", []).append(asyncio.current_task())
        self._rec.setdefault("spawn_envs", []).append(self._env)
        return (object(), object())

    async def __aexit__(self, *exc):
        self._rec.setdefault("exit_tasks", []).append(asyncio.current_task())
        return False


def _patch_stdio(monkeypatch, rec: dict, session: _StubSession | None = None):
    """Patch the stdio transport + ClientSession to stubs that capture the spawn env.

    The transport CM is built from the real ``_stdio_params`` so the token-into-env wiring
    under test is actually exercised; only the subprocess launch is stubbed out.
    """
    real_stdio_params = mc._stdio_params

    def fake_transport_cm(server, headers, user_id=None, agent_id=None):
        params = real_stdio_params(server, user_id, agent_id)
        return _StubTransportCM(rec, dict(params.env))

    monkeypatch.setattr(mc, "_transport_cm", fake_transport_cm)
    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: session or _StubSession())
    monkeypatch.setattr(mc, "_capture_init_result", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(mc, "_server_registry", {})
    monkeypatch.setattr(mc, "_active_sessions", {})
    monkeypatch.setattr(mc, "_session_hosts", {})
    import fleetent.tools.registry as tr

    monkeypatch.setattr(tr, "_registry", {})
    yield
    with contextlib.suppress(Exception):
        mc._active_sessions.clear()
    if isinstance(getattr(mc, "_session_hosts", None), dict):
        mc._session_hosts.clear()


# ── 5.1 per-user subprocess key + reuse + token into env ───────────────────────


async def test_different_users_spawn_distinct_subprocesses(monkeypatch):
    rec: dict = {}
    _patch_stdio(monkeypatch, rec)
    monkeypatch.setattr(
        mc,
        "resolve_user_token",
        lambda sid, uid, aid=None: UserToken(
            access_token=f"tok-{uid}", refresh_token=None, expires_at=None, scope=None
        ),
    )
    server = _per_user_stdio_server("puo")
    mc._server_registry[(None, "puo")] = server

    await mc._open_session_for(server, None, user_id="uA")
    await mc._open_session_for(server, None, user_id="uB")

    assert (None, "puo", "uA") in mc._session_hosts
    assert (None, "puo", "uB") in mc._session_hosts
    # Two distinct spawns; each carries its own user's token in env.
    envs = rec["spawn_envs"]
    assert len(envs) == 2
    token_var = mc._stdio_token_env_name(server)
    assert {e[token_var] for e in envs} == {"tok-uA", "tok-uB"}

    await mc.aclose_all()


async def test_same_user_reuses_subprocess(monkeypatch):
    rec: dict = {}
    _patch_stdio(monkeypatch, rec)
    monkeypatch.setattr(
        mc,
        "resolve_user_token",
        lambda *a, **k: UserToken(
            access_token="t", refresh_token=None, expires_at=None, scope=None
        ),
    )
    server = _per_user_stdio_server("puo")
    mc._server_registry[(None, "puo")] = server

    await mc._open_session_for(server, None, user_id="uA")
    # call_tool with a live session must reuse it, not re-spawn.
    await mc.call_tool("puo", "do", {}, user_id="uA")

    assert len(rec["spawn_envs"]) == 1
    await mc.aclose_all()


async def test_token_env_name_configurable_and_default(monkeypatch):
    custom = _per_user_stdio_server("c", token_env="MY_TOKEN")
    assert mc._stdio_token_env_name(custom) == "MY_TOKEN"
    default = _per_user_stdio_server("d")
    assert mc._stdio_token_env_name(default) == mc._DEFAULT_STDIO_TOKEN_ENV


def test_plain_stdio_env_has_no_token(monkeypatch):
    """A non-per-user stdio server's env is byte-identical (no token var injected)."""
    monkeypatch.setattr(
        mc,
        "resolve_user_token",
        lambda *a, **k: UserToken("X", None, None, None),
    )
    server = _plain_stdio_server("plain")
    params = mc._stdio_params(server, "uA", None)
    assert mc._DEFAULT_STDIO_TOKEN_ENV not in params.env


# ── 5.2 owner-task lifecycle ───────────────────────────────────────────────────


async def test_owner_task_enters_and_exits_same_task(monkeypatch):
    rec: dict = {}
    _patch_stdio(monkeypatch, rec)
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: UserToken("t", None, None, None))
    server = _per_user_stdio_server("puo")
    mc._server_registry[(None, "puo")] = server

    await mc._open_session_for(server, None, user_id="uA")
    # Close from a DIFFERENT task — the cross-task condition that crashed prod.
    await asyncio.create_task(mc.aclose_all())

    assert rec["enter_tasks"][0] is rec["exit_tasks"][0], (
        "stdio subprocess transport entered and exited in different tasks"
    )


async def test_reaper_signals_owner_not_cross_task_unwind(monkeypatch):
    """The idle reaper must close a host via its close_event, on the host's own task."""
    rec: dict = {}
    _patch_stdio(monkeypatch, rec)
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: UserToken("t", None, None, None))
    server = _per_user_stdio_server("puo")
    mc._server_registry[(None, "puo")] = server

    now = {"t": 1000.0}
    monkeypatch.setattr(mc, "_stdio_clock", lambda: now["t"])

    await mc._open_session_for(server, None, user_id="uA")
    enter_task = rec["enter_tasks"][0]

    # Advance past the idle timeout; reap.
    now["t"] += mc._STDIO_IDLE_TIMEOUT + 1
    await mc._reap_idle_stdio_hosts()

    assert (None, "puo", "uA") not in mc._session_hosts, "idle host must be reaped"
    # Exit ran on the SAME task that entered (owner-task self-teardown, not cross-task).
    assert rec["exit_tasks"][0] is enter_task


async def test_reaper_keeps_recently_used_host(monkeypatch):
    rec: dict = {}
    _patch_stdio(monkeypatch, rec)
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: UserToken("t", None, None, None))
    server = _per_user_stdio_server("puo")
    mc._server_registry[(None, "puo")] = server

    now = {"t": 1000.0}
    monkeypatch.setattr(mc, "_stdio_clock", lambda: now["t"])

    await mc._open_session_for(server, None, user_id="uA")
    now["t"] += mc._STDIO_IDLE_TIMEOUT - 1  # still within the idle window
    await mc._reap_idle_stdio_hosts()

    assert (None, "puo", "uA") in mc._session_hosts
    await mc.aclose_all()


# ── 5.3 token-expiry / 401 restart ─────────────────────────────────────────────


async def test_expired_token_restarts_subprocess(monkeypatch):
    rec: dict = {}
    _patch_stdio(monkeypatch, rec)
    server = _per_user_stdio_server("puo")
    mc._server_registry[(None, "puo")] = server

    now = {"t": 1000.0}
    monkeypatch.setattr(mc, "_stdio_clock", lambda: now["t"])

    # First spawn: token expires at t=1100. After refresh: a far-future token.
    tokens = iter(
        [
            UserToken("tok-old", None, 1100.0, None),
            UserToken("tok-old", None, 1100.0, None),  # captured again at spawn (env)
            UserToken("tok-new", None, 9999.0, None),
            UserToken("tok-new", None, 9999.0, None),
        ]
    )
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: next(tokens))

    await mc._open_session_for(server, None, user_id="uA")
    spawn_count_before = len(rec["spawn_envs"])

    # Token now expired → the next call restarts the subprocess with the refreshed token.
    now["t"] = 2000.0
    await mc.call_tool("puo", "do", {}, user_id="uA")

    assert len(rec["spawn_envs"]) == spawn_count_before + 1, "expired token must re-spawn"
    token_var = mc._stdio_token_env_name(server)
    assert rec["spawn_envs"][-1][token_var] == "tok-new"
    await mc.aclose_all()


async def test_401_restarts_subprocess_and_retries(monkeypatch):
    rec: dict = {}
    # First session 401s; the retry session succeeds.
    first = _StubSession(
        raise_on_call=mc.httpx.HTTPStatusError(
            "401",
            request=mc.httpx.Request("POST", "http://x"),
            response=mc.httpx.Response(401),
        )
    )
    second = _StubSession()
    sessions = iter([first, second])
    real_stdio_params = mc._stdio_params

    def fake_transport_cm(server, headers, user_id=None, agent_id=None):
        params = real_stdio_params(server, user_id, agent_id)
        return _StubTransportCM(rec, dict(params.env))

    monkeypatch.setattr(mc, "_transport_cm", fake_transport_cm)
    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: next(sessions))
    monkeypatch.setattr(mc, "_capture_init_result", lambda *a, **k: None)
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: UserToken("t", None, None, None))

    server = _per_user_stdio_server("puo")
    mc._server_registry[(None, "puo")] = server

    await mc._open_session_for(server, None, user_id="uA")
    out = await mc.call_tool("puo", "do", {}, user_id="uA")

    assert out == "ok"  # retry on the fresh subprocess succeeded
    assert len(rec["spawn_envs"]) == 2  # original + restart
    await mc.aclose_all()


# ── 5.4 caps + eviction + orphan cleanup ───────────────────────────────────────


async def test_per_user_cap_evicts_lru_and_logs(monkeypatch, caplog):
    rec: dict = {}
    _patch_stdio(monkeypatch, rec)
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: UserToken("t", None, None, None))
    monkeypatch.setattr(mc, "_STDIO_MAX_PER_USER", 1)
    monkeypatch.setattr(mc, "_STDIO_MAX_TOTAL", 100)

    now = {"t": 1000.0}
    monkeypatch.setattr(mc, "_stdio_clock", lambda: now["t"])

    s1 = _per_user_stdio_server("s1")
    s2 = _per_user_stdio_server("s2")
    mc._server_registry[(None, "s1")] = s1
    mc._server_registry[(None, "s2")] = s2

    await mc._open_session_for(s1, None, user_id="uA")
    now["t"] += 10
    with caplog.at_level("WARNING"):
        await mc._open_session_for(s2, None, user_id="uA")  # uA now over per-user cap

    # The older (s1) host for uA was evicted to honor the per-user cap.
    assert (None, "s1", "uA") not in mc._session_hosts
    assert (None, "s2", "uA") in mc._session_hosts
    assert any("evict" in r.message.lower() for r in caplog.records), "eviction must be logged"
    await mc.aclose_all()


async def test_total_cap_evicts_globally_lru_and_logs(monkeypatch, caplog):
    rec: dict = {}
    _patch_stdio(monkeypatch, rec)
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: UserToken("t", None, None, None))
    monkeypatch.setattr(mc, "_STDIO_MAX_PER_USER", 100)
    monkeypatch.setattr(mc, "_STDIO_MAX_TOTAL", 1)

    now = {"t": 1000.0}
    monkeypatch.setattr(mc, "_stdio_clock", lambda: now["t"])

    server = _per_user_stdio_server("puo")
    mc._server_registry[(None, "puo")] = server

    await mc._open_session_for(server, None, user_id="uA")
    now["t"] += 10
    with caplog.at_level("WARNING"):
        await mc._open_session_for(server, None, user_id="uB")

    # Global cap of 1 → the least-recently-used (uA) host evicted for uB.
    assert (None, "puo", "uA") not in mc._session_hosts
    assert (None, "puo", "uB") in mc._session_hosts
    assert any("evict" in r.message.lower() for r in caplog.records)
    await mc.aclose_all()


async def test_orphan_cleanup_hook_closes_all_stdio(monkeypatch):
    rec: dict = {}
    _patch_stdio(monkeypatch, rec)
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: UserToken("t", None, None, None))
    server = _per_user_stdio_server("puo")
    mc._server_registry[(None, "puo")] = server

    await mc._open_session_for(server, None, user_id="uA")
    await mc._open_session_for(server, None, user_id="uB")

    await mc.cleanup_orphan_stdio_hosts()

    assert not [k for k in mc._session_hosts if len(k) == 3], "all per-user stdio hosts cleaned"
    assert len(rec["exit_tasks"]) == 2


async def test_caps_do_not_touch_plain_servers(monkeypatch):
    """Plain (non-per-user) hosts are exempt from the per-user cap accounting."""
    rec: dict = {}
    _patch_stdio(monkeypatch, rec)
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: UserToken("t", None, None, None))
    monkeypatch.setattr(mc, "_STDIO_MAX_TOTAL", 1)
    monkeypatch.setattr(mc, "_STDIO_MAX_PER_USER", 1)

    plain = _plain_stdio_server("plain")
    mc._server_registry[(None, "plain")] = plain
    await mc._open_session_for(plain, None, user_id=None)

    puo = _per_user_stdio_server("puo")
    mc._server_registry[(None, "puo")] = puo
    # Opening a per-user host must not evict the plain host (not counted in caps).
    await mc._open_session_for(puo, None, user_id="uA")

    assert (None, "plain") in mc._session_hosts
    assert (None, "puo", "uA") in mc._session_hosts
    await mc.aclose_all()


# ── 5.6 shutdown bulkheading ───────────────────────────────────────────────────


async def test_shutdown_contains_per_host_teardown_failure(monkeypatch):
    """One stdio host failing teardown must not block the others or raise from aclose_all."""
    rec: dict = {}

    class _BoomCM(_StubTransportCM):
        async def __aexit__(self, *exc):
            await super().__aexit__(*exc)
            raise RuntimeError("teardown boom")

    real_stdio_params = mc._stdio_params

    def fake_transport_cm(server, headers, user_id=None, agent_id=None):
        params = real_stdio_params(server, user_id, agent_id)
        cls = _BoomCM if server.id == "boom" else _StubTransportCM
        return cls(rec, dict(params.env))

    monkeypatch.setattr(mc, "_transport_cm", fake_transport_cm)
    monkeypatch.setattr(mc, "ClientSession", lambda *a, **k: _StubSession())
    monkeypatch.setattr(mc, "_capture_init_result", lambda *a, **k: None)
    monkeypatch.setattr(mc, "resolve_user_token", lambda *a, **k: UserToken("t", None, None, None))

    boom = _per_user_stdio_server("boom")
    ok = _per_user_stdio_server("ok")
    mc._server_registry[(None, "boom")] = boom
    mc._server_registry[(None, "ok")] = ok
    await mc._open_session_for(boom, None, user_id="uA")
    await mc._open_session_for(ok, None, user_id="uA")

    await mc.aclose_all()  # must not raise despite the boom host

    assert mc._session_hosts == {}
    assert mc._active_sessions == {}
