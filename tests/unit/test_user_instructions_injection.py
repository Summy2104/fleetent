"""Unit tests: user.md injection into the system-prompt stable prefix.

`_assemble_prompt` ordering is a pure function; run_stream wiring is driven with a
mocked LLM (no DB), mirroring test_run_stream_output_firewall.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as al
from fleetent import paths
from fleetent.runtime import user_instructions as ui

# --- _assemble_prompt ordering (pure) ---------------------------------------


def test_assemble_inserts_user_instructions_between_base_and_skills() -> None:
    msgs = al._assemble_prompt(
        "BASE", "SKILLS_CATALOG", {"role": "user", "content": "hi"}, user_instructions="DIRECTIVE"
    )
    sys = msgs[0]["content"]
    assert msgs[0]["role"] == "system"
    assert sys.index("BASE") < sys.index("DIRECTIVE") < sys.index("SKILLS_CATALOG")


def test_assemble_empty_user_instructions_identical_to_legacy() -> None:
    user_msg = {"role": "user", "content": "hi"}
    with_empty = al._assemble_prompt("BASE", "SKILLS", user_msg, user_instructions="")
    legacy = al._assemble_prompt("BASE", "SKILLS", user_msg)
    assert with_empty == legacy


def test_assemble_empty_instructions_and_skills_just_base() -> None:
    msgs = al._assemble_prompt("BASE", "", {"role": "user", "content": "hi"}, user_instructions="")
    # base_system is always augmented with the memory system note; no instructions
    # or skills appended when both are empty.
    content = msgs[0]["content"]
    assert content.startswith("BASE\n\n[记忆系统说明]")
    assert "[用户指令]" not in content
    assert "[SKILLS]" not in content


# --- run_stream wiring (mocked LLM) -----------------------------------------


@pytest.fixture
def mock_client(monkeypatch) -> AsyncMock:
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.params = {}
    cfg.fallbacks = ()
    monkeypatch.setattr(
        al, "get_async_client_and_config", lambda *a, **kw: (client, cfg), raising=False
    )
    monkeypatch.setattr(al, "_build_async_client", lambda resolved, api_key: client)
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "run_pipeline_from_conversation", AsyncMock())
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(al, "evaluate_risk_level", lambda name, args, ctx: "none")
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return client


async def _stream_text(text: str):
    c = MagicMock()
    c.usage = None
    c.choices = [MagicMock()]
    c.choices[0].delta.content = text
    c.choices[0].delta.tool_calls = None
    c.choices[0].delta.reasoning_content = None
    c.choices[0].finish_reason = "stop"
    yield c


async def test_run_stream_injects_user_md_after_base(mock_client) -> None:
    p = paths.agent_home_dir("aid") / ui.USER_MD_FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("永远用中文回答", encoding="utf-8")

    captured: list = []

    async def _create(**kwargs):
        captured.append(kwargs.get("messages"))
        return _stream_text("done")

    mock_client.chat.completions.create = _create

    _ = [e async for e in al.run_stream("hi", agent_name="aid", system_prompt="BASE_SYS")]

    assert captured, "model was never called"
    sys_msg = next(m for m in captured[0] if m["role"] == "system")
    content = sys_msg["content"]
    assert "永远用中文回答" in content
    assert content.index("BASE_SYS") < content.index("永远用中文回答")


async def test_run_stream_no_user_md_omits_block(mock_client) -> None:
    captured: list = []

    async def _create(**kwargs):
        captured.append(kwargs.get("messages"))
        return _stream_text("done")

    mock_client.chat.completions.create = _create

    _ = [e async for e in al.run_stream("hi", agent_name="no-such-agent", system_prompt="BASE_SYS")]

    sys_msg = next(m for m in captured[0] if m["role"] == "system")
    assert "[用户指令]" not in sys_msg["content"]
