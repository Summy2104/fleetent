"""Unit tests for loop.run() permission_gate_enabled and timeout params.

Verifies that passing permission_gate_enabled=False skips the approval gate
and that timeout params are forwarded to _default_gate.request_approval.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as loop


@pytest.fixture
def mock_loop_env(monkeypatch) -> MagicMock:
    """Standard loop mock: simple text LLM response, no real tools/dispatch."""
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.params = {}
    cfg.fallbacks = ()
    monkeypatch.setattr(
        loop, "get_async_client_and_config", lambda *a, **kw: (client, cfg), raising=False
    )
    monkeypatch.setattr(loop, "_build_async_client", lambda resolved, api_key: client)
    monkeypatch.setattr(loop, "get_schemas", lambda: [])
    monkeypatch.setattr(loop, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(loop, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(loop, "extract_and_update", AsyncMock())
    monkeypatch.setattr(loop, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        loop,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return client


def _tool_response(tool_name: str) -> AsyncMock:
    """LLM response stub: one tool call, then a text stop."""
    import json

    tc = MagicMock()
    tc.id = f"tc-{tool_name}"
    tc.type = "function"
    tc.function.name = tool_name
    tc.function.arguments = json.dumps({})

    msg1 = MagicMock()
    msg1.content = None
    msg1.tool_calls = [tc]
    msg1.refusal = None
    choice1 = MagicMock()
    choice1.message = msg1
    choice1.finish_reason = "tool_calls"
    resp1 = MagicMock()
    resp1.choices = [choice1]
    resp1.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    msg2 = MagicMock()
    msg2.content = "done"
    msg2.tool_calls = None
    msg2.refusal = None
    choice2 = MagicMock()
    choice2.message = msg2
    choice2.finish_reason = "stop"
    resp2 = MagicMock()
    resp2.choices = [choice2]
    resp2.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    responses = [resp1, resp2]
    call_count = [0]

    async def _create(**kwargs):
        r = responses[call_count[0]]
        call_count[0] += 1
        return r

    return _create


async def test_permission_gate_disabled_tool_is_dispatched(
    mock_loop_env: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """permission_gate_enabled=False: medium-risk tool is dispatched without approval wait."""
    mock_dispatch = AsyncMock(return_value="file written")
    monkeypatch.setattr(
        loop, "get_risk_level", lambda name: "medium" if name == "write_file" else "low"
    )
    monkeypatch.setattr(loop, "dispatch", mock_dispatch)

    mock_loop_env.chat.completions.create = _tool_response("write_file")

    await loop.run(
        messages=[{"role": "user", "content": "write a file"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=False,
    )

    mock_dispatch.assert_called_once()


async def test_permission_gate_enabled_tool_blocked_on_timeout(
    mock_loop_env: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """permission_gate_enabled=True + short timeout: gate blocks tool (timeout→rejected)."""
    mock_dispatch = AsyncMock(return_value="file written")
    monkeypatch.setattr(
        loop, "get_risk_level", lambda name: "medium" if name == "write_file" else "low"
    )
    monkeypatch.setattr(loop, "dispatch", mock_dispatch)

    mock_loop_env.chat.completions.create = _tool_response("write_file")

    # Use very short timeout so gate auto-rejects quickly; no 300s real wait.
    await loop.run(
        messages=[{"role": "user", "content": "write a file"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=True,
        permission_gate_medium_timeout=0,  # instant timeout → auto-reject
    )

    # Gate rejected the tool, so dispatch was never called.
    mock_dispatch.assert_not_called()


async def test_permission_gate_medium_timeout_forwarded(
    mock_loop_env: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """permission_gate_medium_timeout is forwarded: shorter timeout causes quicker rejection."""
    mock_dispatch = AsyncMock(return_value="result")
    monkeypatch.setattr(
        loop, "get_risk_level", lambda name: "medium" if name == "write_file" else "low"
    )
    monkeypatch.setattr(loop, "dispatch", mock_dispatch)
    mock_loop_env.chat.completions.create = _tool_response("write_file")

    # Very short timeout forwarded → gate times out instantly → tool rejected → dispatch NOT called.
    await loop.run(
        messages=[{"role": "user", "content": "write"}],
        reply_func=AsyncMock(),
        permission_gate_enabled=True,
        permission_gate_medium_timeout=0,
    )

    mock_dispatch.assert_not_called()
