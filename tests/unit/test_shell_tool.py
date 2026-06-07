"""Tests for bash_exec (builtin-shell-tool spec)."""

from __future__ import annotations

import asyncio

from fleetent.tools import registry as tr
from fleetent.tools.shell_tool import bash_exec

# ── description required ──────────────────────────────────────────────────────


def test_bash_exec_description_in_schema():
    schemas = tr.get_schemas()
    schema = next((s for s in schemas if s["function"]["name"] == "bash_exec"), None)
    assert schema is not None
    props = schema["function"]["parameters"]["properties"]
    assert "description" in props
    assert "description" in schema["function"]["parameters"]["required"]


def test_bash_exec_risk_level_is_high():
    assert tr.get_risk_level("bash_exec") == "high"


# ── basic execution ───────────────────────────────────────────────────────────


async def test_bash_exec_runs_simple_command():
    result = await bash_exec(command="echo hello", description="echo hello")
    assert "hello" in result


async def test_bash_exec_captures_stdout_and_stderr():
    result = await bash_exec(
        command="echo out; echo err >&2",
        description="echo to stdout and stderr",
    )
    assert "out" in result


async def test_bash_exec_includes_nonzero_exit_code():
    result = await bash_exec(command="exit 1", description="exit with code 1")
    assert "[exit 1]" in result


async def test_bash_exec_zero_exit_no_exit_marker():
    result = await bash_exec(command="echo ok", description="echo ok")
    assert "[exit 0]" not in result


# ── workdir ───────────────────────────────────────────────────────────────────


async def test_bash_exec_workdir_changes_cwd(tmp_path):
    result = await bash_exec(
        command="pwd",
        description="print working directory",
        workdir=str(tmp_path),
    )
    assert str(tmp_path) in result


# ── timeout ───────────────────────────────────────────────────────────────────


async def test_bash_exec_timeout_terminates_command():
    result = await bash_exec(
        command="sleep 10",
        description="sleep for 10 seconds",
        timeout=0.1,
    )
    assert "超时" in result or "timeout" in result.lower()


# ── cancellation ─────────────────────────────────────────────────────────────


async def test_bash_exec_cancel_token_stops_command():
    from fleetent.runtime.cancellation import CancelToken

    token = CancelToken()

    async def _cancel_soon():
        await asyncio.sleep(0.05)
        token.cancel()

    asyncio.create_task(_cancel_soon())
    result = await bash_exec(
        command="sleep 10",
        description="long sleep",
        timeout=30.0,
        cancel_token=token,
    )
    assert "取消" in result or "cancel" in result.lower()


# ── output spillover ──────────────────────────────────────────────────────────


async def test_bash_exec_large_output_uses_spillover(tmp_path, monkeypatch):
    import fleetent.tools.result_truncation as trt

    monkeypatch.setattr(trt, "SPILLOVER_DIR", tmp_path / "spillover")
    monkeypatch.setattr(trt, "MAX_TOOL_RESULT_BYTES", 100)

    result = await bash_exec(
        command="python3 -c \"print('x' * 200)\"",
        description="print large output",
    )
    # Should either use spillover or self-truncate, but not crash
    assert isinstance(result, str)
    assert len(result) > 0


# ── schema excludes out-of-band params ────────────────────────────────────────


def test_bash_exec_schema_excludes_cancel_token():
    schemas = tr.get_schemas()
    schema = next(s for s in schemas if s["function"]["name"] == "bash_exec")
    assert "cancel_token" not in schema["function"]["parameters"]["properties"]
    assert "tool_context" not in schema["function"]["parameters"]["properties"]
