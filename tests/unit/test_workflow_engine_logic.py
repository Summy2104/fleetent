"""Unit tests for engine pure logic: readiness, cascade-skip, terminal status."""

from fleetent.workflow.definition import parse_definition
from fleetent.workflow.engine import (
    compute_cascade_skips,
    compute_ready,
    compute_run_terminal_status,
)


def _wf():
    return parse_definition(
        {
            "name": "demo",
            "steps": [
                {"id": "a", "type": "agent", "prompt": "x"},
                {"id": "b", "type": "agent", "prompt": "x", "depends_on": ["a"]},
                {"id": "c", "type": "notify", "text": "${steps.b.output.text}"},
            ],
        }
    )


def test_ready_only_when_all_preds_succeeded():
    wf = _wf()
    assert compute_ready(wf, {"a": "pending", "b": "pending", "c": "pending"}) == ["a"]
    assert set(compute_ready(wf, {"a": "succeeded", "b": "pending", "c": "pending"})) == {"b"}
    assert compute_ready(wf, {"a": "succeeded", "b": "succeeded", "c": "pending"}) == ["c"]


def test_running_step_not_ready():
    wf = _wf()
    assert compute_ready(wf, {"a": "running", "b": "pending", "c": "pending"}) == []


def test_cascade_skip_on_failed_pred():
    wf = _wf()
    skips = compute_cascade_skips(wf, {"a": "failed", "b": "pending", "c": "pending"})
    assert "b" in skips


def test_terminal_status_none_when_incomplete():
    assert compute_run_terminal_status({"a": "succeeded", "b": "running"}) is None


def test_terminal_status_failed_dominates():
    assert (
        compute_run_terminal_status({"a": "succeeded", "b": "failed", "c": "skipped"}) == "failed"
    )


def test_terminal_status_cancelled():
    assert compute_run_terminal_status({"a": "succeeded", "b": "cancelled"}) == "cancelled"


def test_terminal_status_succeeded():
    assert compute_run_terminal_status({"a": "succeeded", "b": "succeeded"}) == "succeeded"
