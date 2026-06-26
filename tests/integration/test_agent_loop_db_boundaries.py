"""DB-backed agent loop boundary tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as al


def _text_resp(text: str | None = "reply") -> MagicMock:
    msg = MagicMock()
    msg.content = text
    msg.tool_calls = None
    msg.model_dump = lambda: {"role": "assistant", "content": text}

    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    return resp


def _tool_resp(name: str, args: str = "{}", call_id: str = "tc-1") -> MagicMock:
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = name
    tc.function.arguments = args

    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]
    msg.model_dump = lambda: {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": args}}
        ],
    }

    choice = MagicMock()
    choice.finish_reason = "tool_calls"
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock()
    return resp


@pytest.fixture
def mock_client(monkeypatch) -> AsyncMock:
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.fallbacks = ()

    monkeypatch.setattr(al, "_build_async_client", lambda resolved, api_key: client)
    monkeypatch.setattr(al, "get_schemas", lambda: [])
    monkeypatch.setattr(al, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(al, "run_pipeline_from_conversation", AsyncMock())
    monkeypatch.setattr(al, "dispatch", lambda name, args, **kw: f"{name}_result")
    monkeypatch.setattr(al, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        al,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return client


def _bind_context_state_db(cm, monkeypatch, tmp_path):
    """Inject a migrated per-agent agent_state.db into runtime.context (replaces DB_PATH)."""
    from fleetent.runtime.agent_state_migrations import MIGRATIONS
    from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    db = router.agent_scope("default", "agent").open_state_db(MIGRATIONS)
    monkeypatch.setattr(cm, "_state_db", db)
    return db


async def test_run_loads_and_saves_flap_state(mock_client, monkeypatch, tmp_path):
    import fleetent.runtime.context as cm
    from fleetent.runtime.context import AntiFlapState

    _bind_context_state_db(cm, monkeypatch, tmp_path)
    cm.save_anti_flap_state("sess-flap", AntiFlapState(turns_since_last_compress=7))

    captured: dict = {}

    def fake_apply(messages, state, config=None, **kw):
        captured["in_turns"] = state.turns_since_last_compress
        return messages, AntiFlapState(turns_since_last_compress=99, auto_disabled=True)

    monkeypatch.setattr(al, "apply_anti_flap", fake_apply)
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("done"))

    await al.run([{"role": "user", "content": "x"}], session_id="sess-flap")

    assert captured["in_turns"] == 7  # loaded prior state from users.db
    saved = cm.load_anti_flap_state("sess-flap")
    assert saved.turns_since_last_compress == 99 and saved.auto_disabled is True  # saved back


async def test_run_without_session_id_does_not_touch_flap_db(mock_client, monkeypatch, tmp_path):
    import fleetent.runtime.context as cm

    # Bind a fresh per-agent state DB; with no session_id the loop must not engage anti-flap
    # at all, so nothing is written to session_anti_flap.
    db = _bind_context_state_db(cm, monkeypatch, tmp_path)
    called = {"apply": 0}
    monkeypatch.setattr(
        al, "apply_anti_flap", lambda *a, **k: called.__setitem__("apply", called["apply"] + 1)
    )
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("done"))
    await al.run([{"role": "user", "content": "x"}])  # no session_id
    assert called["apply"] == 0  # ungated AR12 path; anti-flap not engaged
    rows = db.execute("SELECT COUNT(*) AS n FROM session_anti_flap").fetchone()
    assert rows["n"] == 0  # no anti-flap state persisted
