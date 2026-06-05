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


def test_agentfile_has_sub_agent_timeout_default_300():
    from fleetent.agent_config import AgentFile

    assert AgentFile(name="x", version=1).sub_agent_timeout_seconds == 300
