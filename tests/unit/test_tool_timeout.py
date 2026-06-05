"""Tests for per-tool timeout protection at the dispatch boundary (T2)."""

import asyncio

import fleetent.runtime.loop as al
import fleetent.tools.registry as tr
from fleetent.runtime.cancellation import CancelToken


def _register(monkeypatch, name, fn, timeout=None):
    monkeypatch.setitem(tr._registry, name, (fn, tr._build_schema(fn)))
    if timeout is not None:
        monkeypatch.setitem(tr._timeouts, name, timeout)


# ── per-tool timeout metadata (group 2) ──────────────────────────────────────


def test_tool_timeout_recorded():
    @tr.tool(timeout=5)
    def _t_with_timeout() -> str:
        return "x"

    assert tr.get_timeout("_t_with_timeout") == 5


def test_undeclared_tool_timeout_is_none():
    @tr.tool
    def _t_no_timeout() -> str:
        return "x"

    assert tr.get_timeout("_t_no_timeout") is None


def test_timeout_metadata_not_in_schema():
    @tr.tool(timeout=5)
    def _t_schema(query: str) -> str:
        return query

    schema = next(s for s in tr.get_schemas() if s["function"]["name"] == "_t_schema")
    props = schema["function"]["parameters"]["properties"]
    assert "timeout" not in props
    assert "query" in props


# ── effective timeout resolution (group 3) ───────────────────────────────────


def test_effective_timeout_uses_per_tool(monkeypatch):
    _register(monkeypatch, "_eff_a", lambda: "x", timeout=7.0)
    assert tr.get_effective_timeout("_eff_a") == 7.0


def test_effective_timeout_falls_back_to_default(monkeypatch):
    _register(monkeypatch, "_eff_b", lambda: "x")
    assert tr.get_effective_timeout("_eff_b") == tr.DEFAULT_TOOL_TIMEOUT


def test_default_tool_timeout_is_30():
    assert tr.DEFAULT_TOOL_TIMEOUT == 30.0


def test_effective_timeout_default_injectable(monkeypatch):
    _register(monkeypatch, "_eff_c", lambda: "x")
    monkeypatch.setattr(tr, "DEFAULT_TOOL_TIMEOUT", 99.0)
    assert tr.get_effective_timeout("_eff_c") == 99.0


# ── timeout race in _safe_dispatch (group 4) ─────────────────────────────────


async def test_safe_dispatch_times_out_noncooperative(monkeypatch):
    async def _slow() -> str:
        await asyncio.sleep(10)
        return "done"

    _register(monkeypatch, "_slow", _slow, timeout=0.01)
    result, failed = await al._safe_dispatch("_slow", {}, is_sub_agent=False)
    assert failed is True
    assert "timeout" in result.lower() or "timed out" in result.lower()


async def test_safe_dispatch_normal_unaffected(monkeypatch):
    async def _fast() -> str:
        return "ok"

    _register(monkeypatch, "_fast", _fast, timeout=5)
    result, failed = await al._safe_dispatch("_fast", {}, is_sub_agent=False)
    assert (result, failed) == ("ok", False)


async def test_safe_dispatch_injects_token_with_deadline(monkeypatch):
    captured: dict[str, object] = {}

    async def _coop(cancel_token: CancelToken | None = None) -> str:
        captured["token"] = cancel_token
        return "ok"

    _register(monkeypatch, "_coop", _coop, timeout=5)
    await al._safe_dispatch("_coop", {}, is_sub_agent=False)
    tok = captured["token"]
    assert isinstance(tok, CancelToken)
    assert tok.deadline is not None


async def test_safe_dispatch_token_cancelled_on_timeout(monkeypatch):
    captured: dict[str, object] = {}

    async def _slow(cancel_token: CancelToken | None = None) -> str:
        captured["token"] = cancel_token
        await asyncio.sleep(10)
        return "done"

    _register(monkeypatch, "_slowtok", _slow, timeout=0.01)
    result, failed = await al._safe_dispatch("_slowtok", {}, is_sub_agent=False)
    assert failed is True
    assert captured["token"].is_cancelled() is True  # deadline passed / cancelled


async def test_safe_dispatch_run_level_cancel_via_parent(monkeypatch):
    async def _coop(cancel_token: CancelToken | None = None) -> str:
        return "cancelled" if cancel_token.is_cancelled() else "live"

    _register(monkeypatch, "_coop2", _coop, timeout=300)
    run_token = CancelToken()
    run_token.cancel()  # whole session cancelled before this tool's own deadline
    result, failed = await al._safe_dispatch(
        "_coop2", {}, is_sub_agent=False, cancel_token=run_token
    )
    # The per-tool token must OR in the run-level cancel via parent linkage.
    assert result == "cancelled"


# ── SB7 boundary (group 6) ───────────────────────────────────────────────────


async def test_timeout_is_plain_await_stop_no_sandbox(monkeypatch):
    # A generic (non-sandbox) async tool times out purely at the await layer:
    # the main loop gets a tool_timeout failure with no container kill involved.
    async def _slow() -> str:
        await asyncio.sleep(10)
        return "done"

    _register(monkeypatch, "_generic_slow", _slow, timeout=0.01)
    result, failed = await al._safe_dispatch("_generic_slow", {}, is_sub_agent=False)
    assert failed is True
    from fleetent.runtime.error_classifier import ErrorCategory, classify

    assert classify(TimeoutError()).category is ErrorCategory.tool_timeout


# ── T2 review: global default timeout configurable via Settings ──────────────


def test_agentfile_tool_default_timeout_default_30():
    from fleetent.agent_config import AgentFile, default_models

    assert (
        AgentFile(name="x", version=1, models=default_models()).tool_default_timeout_seconds == 30.0
    )


def test_get_effective_timeout_honors_passed_default(monkeypatch):
    _register(monkeypatch, "_eff_def", lambda: "x")  # no per-tool timeout
    assert tr.get_effective_timeout("_eff_def", 12.5) == 12.5  # uses supplied default
    assert tr.get_effective_timeout("_eff_def") == tr.DEFAULT_TOOL_TIMEOUT  # falls back


def test_resolve_default_tool_timeout_uses_governance_default():
    import fleetent.runtime.loop as al

    # No governance → the GovernanceConfig literal default (per-agent knob otherwise).
    assert al._resolve_default_tool_timeout() == 30.0
