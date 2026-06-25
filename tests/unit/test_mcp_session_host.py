"""MCP session host (per-session owner task) lifecycle.

Regression guard for the 2026-06-11 graceful-shutdown crash: the SDK transport context
managers use anyio cancel scopes that MUST be entered and exited in the same task. A
shared module-level AsyncExitStack entered by one task and unwound by another violates
this and crashes the process on teardown. Each session must be owned by a dedicated
host task so enter/exit always happen in the same task.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest


def _server(transport: str = "http", sid: str = "s1"):
    from fleetent.integrations.mcp.client import McpServerConfig

    return McpServerConfig(id=sid, transport=transport, url="http://example.test/mcp")


class _StubTransportCM:
    """Records which task enters/exits — the cancel-scope affinity probe."""

    def __init__(self, rec: dict):
        self._rec = rec

    async def __aenter__(self):
        self._rec.setdefault("enter_tasks", []).append(asyncio.current_task())
        return (object(), object())  # (read, write) streams

    async def __aexit__(self, *exc):
        self._rec.setdefault("exit_tasks", []).append(asyncio.current_task())
        return False


class _StubSession:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def initialize(self):
        return type("Init", (), {"capabilities": None, "protocolVersion": "1"})()


def _patch_transport(monkeypatch, rec: dict, *, exit_raises: bool = False):
    from fleetent.integrations.mcp import client

    class _CM(_StubTransportCM):
        async def __aexit__(self, *exc):
            await super().__aexit__(*exc)
            if exit_raises:
                raise RuntimeError("teardown boom")
            return False

    monkeypatch.setattr(client, "_transport_cm", lambda server, headers, *a, **k: _CM(rec))
    monkeypatch.setattr(client, "ClientSession", _StubSession)
    monkeypatch.setattr(client, "_capture_init_result", lambda *a, **k: None)


async def test_session_enter_and_exit_in_same_task(monkeypatch):
    from fleetent.integrations.mcp import client

    rec: dict = {}
    _patch_transport(monkeypatch, rec)

    # Open the session from THIS task.
    await client._open_session_for(_server(), None)
    assert rec["enter_tasks"], "transport must have been entered"

    # Close from a DIFFERENT task — the exact cross-task condition that crashed prod.
    await asyncio.create_task(client.aclose_all())

    assert rec.get("exit_tasks"), "transport must have been exited on close"
    # The architectural invariant: enter and exit happen in the same (host) task,
    # regardless of which task triggered open/close.
    assert rec["enter_tasks"][0] is rec["exit_tasks"][0], (
        "session transport entered and exited in different tasks — anyio cancel-scope violation"
    )


async def test_aclose_all_contains_teardown_errors(monkeypatch):
    from fleetent.integrations.mcp import client

    rec: dict = {}
    _patch_transport(monkeypatch, rec, exit_raises=True)

    await client._open_session_for(_server(sid="boom"), None)
    # A teardown that raises must NOT propagate out of aclose_all.
    await client.aclose_all()  # should not raise
    assert client._active_sessions == {}, "registry cleared even when teardown errored"


async def test_reopen_closes_old_host(monkeypatch):
    from fleetent.integrations.mcp import client

    rec: dict = {}
    _patch_transport(monkeypatch, rec)

    await client._open_session_for(_server(sid="r1"), None)
    first_exit_count = len(rec.get("exit_tasks", []))
    await client._reopen_session(_server(sid="r1"), None)
    # Reopening must have closed the previous host (one more exit recorded).
    assert len(rec.get("exit_tasks", [])) == first_exit_count + 1, (
        "reopen must close the old session host (no leak)"
    )
    await client.aclose_all()


@pytest.fixture(autouse=True)
def _clear_sessions():
    from fleetent.integrations.mcp import client

    yield
    with contextlib.suppress(Exception):
        client._active_sessions.clear()
    hosts = getattr(client, "_session_hosts", None)
    if isinstance(hosts, dict):
        hosts.clear()
