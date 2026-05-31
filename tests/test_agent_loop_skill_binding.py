"""Per-agent skill-injection filtering in agent_loop (opt-in whitelist)."""

from unittest.mock import AsyncMock, MagicMock

import fleetent.agent_loop as al

_SKILL_BODY = "## DEPLOY SKILL\nfollow the runbook."


async def _stream_chunks(*contents, finish="stop"):
    for i, content in enumerate(contents):
        c = MagicMock()
        c.usage = None
        c.choices = [MagicMock()]
        c.choices[0].delta.content = content
        c.choices[0].delta.tool_calls = None
        c.choices[0].finish_reason = finish if i == len(contents) - 1 else None
        yield c


def _wire(monkeypatch):
    """Wire agent_loop with a matchable skill and a system-prompt capture."""
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.fallbacks = ()
    captured: dict[str, str] = {}

    async def fake_create(*, model, messages, **kw):
        captured["system"] = messages[0]["content"]
        return _stream_chunks("ok", None)

    client.chat.completions.create = fake_create
    monkeypatch.setattr(al, "get_async_client_and_config", lambda _: (client, cfg))
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "extract_and_save", lambda *a, **kw: None)
    monkeypatch.setattr(al, "load_memories", lambda **kw: "")
    monkeypatch.setattr(al, "match_skill", lambda _: "deploy")
    monkeypatch.setattr(al, "load_skill", lambda _: _SKILL_BODY)
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return captured


# ── run_stream() ──────────────────────────────────────────────────────────────


async def test_run_stream_injects_skill_when_whitelisted(monkeypatch):
    captured = _wire(monkeypatch)
    _ = [e async for e in al.run_stream("deploy please", allowed_skills=["deploy"])]
    assert _SKILL_BODY in captured["system"]


async def test_run_stream_no_inject_when_not_whitelisted(monkeypatch):
    captured = _wire(monkeypatch)
    _ = [e async for e in al.run_stream("deploy please", allowed_skills=["hr-*"])]
    assert _SKILL_BODY not in captured["system"]


async def test_run_stream_blocklist_excludes_whitelisted_skill(monkeypatch):
    captured = _wire(monkeypatch)
    _ = [
        e
        async for e in al.run_stream(
            "deploy please", allowed_skills=["*"], blocked_skills=["deploy"]
        )
    ]
    assert _SKILL_BODY not in captured["system"]


async def test_run_stream_opt_in_none_does_not_inject(monkeypatch):
    captured = _wire(monkeypatch)
    # allowed_skills defaults to None → opt-in: nothing injected even on a match.
    _ = [e async for e in al.run_stream("deploy please")]
    assert _SKILL_BODY not in captured["system"]


# ── run() (no skill injection of its own — receives prebuilt messages) ─────────


async def test_run_accepts_skill_params_without_error(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.setattr(al, "get_async_client_and_config", lambda _, **kw: _run_client())
    messages = [{"role": "user", "content": "hi"}]
    out = await al.run(messages, allowed_skills=["deploy"], blocked_skills=["x"])
    assert out == "hello"


def _run_client():
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.fallbacks = ()
    msg = MagicMock()
    msg.content = "hello"
    msg.tool_calls = []
    msg.model_dump = lambda: {"role": "assistant", "content": "hello"}
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=resp)
    return client, cfg


# ── run_sync() (CLI) opt-in behavior change ────────────────────────────────────


def test_run_sync_opt_in_does_not_inject_skill(monkeypatch):
    captured: dict[str, list] = {}

    async def fake_run(messages, **kw):
        captured["messages"] = messages
        return "done"

    monkeypatch.setattr(al, "scan_skills", lambda *a, **kw: None)
    monkeypatch.setattr(al, "load_memories", lambda **kw: "")
    monkeypatch.setattr(al, "match_skill", lambda _: "deploy")
    monkeypatch.setattr(al, "load_skill", lambda _: _SKILL_BODY)
    monkeypatch.setattr(al, "run", fake_run)

    al.run_sync("deploy please")
    system = captured["messages"][0]["content"]
    assert _SKILL_BODY not in system
