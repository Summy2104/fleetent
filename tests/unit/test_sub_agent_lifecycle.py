"""Tests for sub-agent lifecycle state machine, persistence and timeout (AR20)."""

import pytest

# ── state machine + dataclass (group 2) ──────────────────────────────────────


def test_state_enum_members():
    from fleetent.runtime.sub_agent_lifecycle import SubAgentState

    assert {s.value for s in SubAgentState} == {
        "pending",
        "running",
        "succeeded",
        "failed",
        "timed_out",
        "cancelled",
    }


def test_lifecycle_dataclass_defaults():
    from fleetent.runtime.sub_agent_lifecycle import SubAgentLifecycle, SubAgentState

    lc = SubAgentLifecycle(
        run_id="r1",
        parent_session_id="s1",
        name="task-a",
        timeout_seconds=300,
        created_at="2026-06-01T00:00:00Z",
    )
    assert lc.state is SubAgentState.pending
    assert lc.started_at is None
    assert lc.ended_at is None
    assert lc.error is None


# ── transition validation (group 3) ──────────────────────────────────────────


@pytest.mark.parametrize(
    "src,dst",
    [
        ("pending", "running"),
        ("running", "succeeded"),
        ("running", "failed"),
        ("running", "timed_out"),
        ("running", "cancelled"),
        ("pending", "cancelled"),
    ],
)
def test_legal_transitions(src, dst):
    from fleetent.runtime.sub_agent_lifecycle import SubAgentState, validate_transition

    validate_transition(SubAgentState(src), SubAgentState(dst))  # no raise


@pytest.mark.parametrize(
    "src,dst",
    [
        ("succeeded", "running"),
        ("pending", "succeeded"),
        ("running", "pending"),
        ("timed_out", "running"),
        ("cancelled", "succeeded"),
    ],
)
def test_illegal_transitions_raise(src, dst):
    from fleetent.runtime.sub_agent_lifecycle import SubAgentState, validate_transition

    with pytest.raises(ValueError):
        validate_transition(SubAgentState(src), SubAgentState(dst))


# ── sqlite3 persistence + query (group 4) ────────────────────────────────────


def _lc(run_id, parent, name="t", state=None):
    from fleetent.runtime.sub_agent_lifecycle import SubAgentLifecycle, SubAgentState

    return SubAgentLifecycle(
        run_id=run_id,
        parent_session_id=parent,
        name=name,
        state=state or SubAgentState.pending,
        timeout_seconds=300,
        created_at="2026-06-01T00:00:00Z",
    )


def test_init_db_idempotent(tmp_path, monkeypatch):
    import fleetent.runtime.sub_agent_lifecycle as sal

    monkeypatch.setattr(sal, "DB_PATH", tmp_path / "users.db")
    sal.init_db()
    sal.upsert(_lc("r1", "s1"))
    sal.init_db()  # second init must not drop data
    rows = sal.query_by_parent("s1")
    assert len(rows) == 1


def test_upsert_then_read_back(tmp_path, monkeypatch):
    import fleetent.runtime.sub_agent_lifecycle as sal

    monkeypatch.setattr(sal, "DB_PATH", tmp_path / "users.db")
    sal.init_db()
    sal.upsert(_lc("r1", "s1", name="alpha"))
    rows = sal.query_by_parent("s1")
    assert rows[0].run_id == "r1"
    assert rows[0].name == "alpha"
    assert rows[0].state is sal.SubAgentState.pending


def test_query_reflects_terminal_state_and_ended_at(tmp_path, monkeypatch):
    import fleetent.runtime.sub_agent_lifecycle as sal

    monkeypatch.setattr(sal, "DB_PATH", tmp_path / "users.db")
    sal.init_db()
    lc = _lc("r1", "s1")
    sal.upsert(lc)
    lc.state = sal.SubAgentState.succeeded
    lc.started_at = "2026-06-01T00:00:01Z"
    lc.ended_at = "2026-06-01T00:00:05Z"
    sal.upsert(lc)
    row = sal.query_by_parent("s1")[0]
    assert row.state is sal.SubAgentState.succeeded
    assert row.ended_at == "2026-06-01T00:00:05Z"


def test_query_by_parent_filters(tmp_path, monkeypatch):
    import fleetent.runtime.sub_agent_lifecycle as sal

    monkeypatch.setattr(sal, "DB_PATH", tmp_path / "users.db")
    sal.init_db()
    sal.upsert(_lc("r1", "s1"))
    sal.upsert(_lc("r2", "s1"))
    sal.upsert(_lc("r3", "s2"))
    assert {r.run_id for r in sal.query_by_parent("s1")} == {"r1", "r2"}
    assert {r.run_id for r in sal.query_by_parent("s2")} == {"r3"}


# ── timeout resolution (group 5) ─────────────────────────────────────────────


def test_default_timeout_constant_is_300():
    from fleetent.runtime.sub_agent_lifecycle import SUB_AGENT_TIMEOUT_SECONDS

    assert SUB_AGENT_TIMEOUT_SECONDS == 300


def test_resolve_timeout_precedence_call_over_config():
    from fleetent.runtime.sub_agent_lifecycle import resolve_timeout

    assert resolve_timeout(5, config=120) == 5


def test_resolve_timeout_config_over_default():
    from fleetent.runtime.sub_agent_lifecycle import resolve_timeout

    assert resolve_timeout(None, config=120) == 120


def test_settings_has_sub_agent_timeout_default_300():
    from fleetent.config import Settings

    assert Settings(anthropic_api_key="x").sub_agent_timeout_seconds == 300
