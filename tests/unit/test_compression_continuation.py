"""Unit tests: structured summary template + active-task continuation block (C3a).

Pure logic + injectable file boundary (monkeypatched SESSIONS_DIR for .todo). No
real LLM (patches _summarize), no platform.
"""

from __future__ import annotations

from pathlib import Path

import fleetent.runtime.context as cm
import fleetent.session.manager as smgr

# ── 1. structured summary template ──────────────────────────────────────────────


def test_summary_prompt_first_pass_is_structured():
    p = cm._build_summary_prompt("the conversation text", None)
    assert "## Next Steps" in p
    assert "In Progress" in p
    assert "the conversation text" in p
    assert "resume" in p.lower()  # continuation intent


def test_summary_prompt_incremental_same_structure():
    p = cm._build_summary_prompt("new messages here", "EXISTING SUMMARY BODY")
    assert "## Next Steps" in p
    assert "In Progress" in p
    assert "EXISTING SUMMARY BODY" in p
    assert "new messages here" in p
    assert "merge" in p.lower()  # merge new into existing sections


# ── 2. active-task continuation block ───────────────────────────────────────────

_CFG = {"max_tokens": 10_000, "tmax_ratio": 0.5, "tretained_ratio": 0.3, "keep_recent": 4}


def _big_msgs(n: int = 100) -> list[dict]:
    return [
        {"role": "system", "content": "sys"},
        *[{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 2000} for i in range(n)],
    ]


def _patch_summary(monkeypatch) -> None:
    monkeypatch.setattr(cm, "_summarize", lambda msgs, prev_summary=None, config=None: "S.")


def _contents(result: list) -> list[str]:
    return [str(m.get("content", "")) for m in result if isinstance(m, dict)]


def test_active_task_block_injected_when_unfinished_todos(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(smgr, "SESSIONS_DIR", tmp_path)
    _patch_summary(monkeypatch)
    smgr.write_todo(
        "sid1",
        [
            {"id": "1", "text": "finish the report", "status": "in_progress"},
            {"id": "2", "text": "already done", "status": "completed"},
        ],
    )
    result = cm.maybe_compress(_big_msgs(), config=_CFG, session_id="sid1")
    contents = _contents(result)
    active = [c for c in contents if c.startswith(cm._ACTIVE_TASK_PREFIX)]
    assert len(active) == 1
    assert "finish the report" in active[0]  # unfinished kept verbatim
    assert "already done" not in active[0]  # completed excluded
    # positioned before the summary message
    active_idx = next(i for i, c in enumerate(contents) if c.startswith(cm._ACTIVE_TASK_PREFIX))
    summary_idx = next(i for i, c in enumerate(contents) if c.startswith(cm._SUMMARY_PREFIX))
    assert active_idx < summary_idx


def test_no_active_task_block_when_all_completed(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(smgr, "SESSIONS_DIR", tmp_path)
    _patch_summary(monkeypatch)
    smgr.write_todo("sid2", [{"id": "1", "text": "x", "status": "completed"}])
    result = cm.maybe_compress(_big_msgs(), config=_CFG, session_id="sid2")
    assert not any(c.startswith(cm._ACTIVE_TASK_PREFIX) for c in _contents(result))


def test_no_active_task_block_without_session(monkeypatch):
    _patch_summary(monkeypatch)
    result = cm.maybe_compress(_big_msgs(), config=_CFG)  # no session_id
    assert not any(c.startswith(cm._ACTIVE_TASK_PREFIX) for c in _contents(result))


def test_no_active_task_block_when_todo_read_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(smgr, "SESSIONS_DIR", tmp_path)
    _patch_summary(monkeypatch)
    (tmp_path / "sid3.todo").write_text("{bad json")  # corrupt → read_todo returns []
    result = cm.maybe_compress(_big_msgs(), config=_CFG, session_id="sid3")
    assert not any(c.startswith(cm._ACTIVE_TASK_PREFIX) for c in _contents(result))
