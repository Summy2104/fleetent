"""DB-backed agent loop boundary tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as al
from fleetent.identity import Principal


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
    monkeypatch.setattr(al, "extract_and_update", AsyncMock())
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


async def test_run_loads_and_saves_flap_state(mock_client, monkeypatch, tmp_path):
    import fleetent.runtime.context as cm
    from fleetent.runtime.context import AntiFlapState

    monkeypatch.setattr(cm, "DB_PATH", tmp_path / "users.db")
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

    monkeypatch.setattr(cm, "DB_PATH", tmp_path / "users.db")
    called = {"apply": 0}
    monkeypatch.setattr(
        al, "apply_anti_flap", lambda *a, **k: called.__setitem__("apply", called["apply"] + 1)
    )
    mock_client.chat.completions.create = AsyncMock(return_value=_text_resp("done"))
    await al.run([{"role": "user", "content": "x"}])  # no session_id
    assert called["apply"] == 0  # ungated AR12 path; anti-flap not engaged
    assert not (tmp_path / "users.db").exists()  # no DB created


async def test_run_layered_budget_trips_and_logs_scope(mock_client, monkeypatch, tmp_path):
    import fleetent.runtime.layered_budget as lbud
    from fleetent.runtime.termination import StopReason

    monkeypatch.setattr(lbud, "DB_PATH", tmp_path / "users.db")
    # Tiny user-token cap -> second checkpoint trips via the layered checker.
    capped = lbud.LayeredBudgetConfig({lbud.BudgetScope.user: lbud.ScopeBudget(max_tokens=1)})
    monkeypatch.setattr(
        lbud.LayeredBudgetConfig, "from_governance", classmethod(lambda cls, g: capped)
    )
    captured: dict = {}
    monkeypatch.setattr(al, "log_run", lambda *a, **kw: captured.update(kw))

    def _resp(*a, **k):
        r = _tool_resp("get_time")
        r.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        return r

    mock_client.chat.completions.create = AsyncMock(side_effect=_resp)

    await al.run([{"role": "user", "content": "x"}], principal=Principal(user_id="u1", tenant_id="default"), session_id="s1", max_turns=50)
    assert captured.get("stop_reason") == StopReason.budget_exceeded
    assert captured.get("budget_scope") == "user"  # layered user scope reported
    from datetime import UTC, datetime

    used = lbud.BudgetStore().get(lbud.BudgetScope.user, "u1", now=datetime.now(UTC))
    assert used.tokens >= 15  # store accumulated across the turn(s)
