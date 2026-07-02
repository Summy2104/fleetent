"""Integration tests for backflow_store PR-link helpers (skill-backflow-git-pr).

Covers: new proposals default NULL PR fields, set_pr_link (COALESCE, partial updates),
set_pr_state (validated), passthrough via get_proposal, and list_by_pr_state for the sweep.
"""

from __future__ import annotations

import pytest

from fleetent.platform.skill_management import backflow_store
from tests.integration._migration_template import apply_migrations


@pytest.fixture
def db(tmp_path, monkeypatch):
    db_path = tmp_path / "mgmt.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def _insert_proposal(
    skill_name: str = "crm-ops", agent_id: int = 1, status: str = "pending"
) -> int:
    with backflow_store._database().transaction() as conn:
        conn.execute(
            "INSERT INTO backflow_proposals "
            "(status, agent_id, skill_name, proposed_bundle, created_at, updated_at) "
            "VALUES (:s, :a, :n, '{}', 'now', 'now')",
            {"s": status, "a": agent_id, "n": skill_name},
        )
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
    assert row is not None
    return int(row["id"])


def test_new_proposal_has_null_pr_fields(db) -> None:
    pid = _insert_proposal()
    proposal = backflow_store.get_proposal(pid)
    assert proposal is not None
    assert proposal["pr_branch"] is None
    assert proposal["pr_state"] is None
    assert proposal["pr_id"] is None
    assert proposal["pr_merge_commit"] is None


def test_set_pr_link_partial_update_is_coalesced(db) -> None:
    pid = _insert_proposal()
    backflow_store.set_pr_link(pid, branch="backflow/support/crm-ops")
    backflow_store.set_pr_state(pid, "backed_up")

    proposal = backflow_store.get_proposal(pid)
    assert proposal is not None
    assert proposal["pr_branch"] == "backflow/support/crm-ops"
    assert proposal["pr_state"] == "backed_up"

    # Setting the PR id/url leaves the previously-set branch intact (COALESCE).
    backflow_store.set_pr_link(pid, pr_id="42", pr_url="https://git/pr/42")
    updated = backflow_store.get_proposal(pid)
    assert updated is not None
    assert updated["pr_branch"] == "backflow/support/crm-ops"
    assert updated["pr_id"] == "42"
    assert updated["pr_url"] == "https://git/pr/42"


def test_set_pr_state_rejects_unknown(db) -> None:
    pid = _insert_proposal()
    with pytest.raises(ValueError):
        backflow_store.set_pr_state(pid, "bogus")


def test_list_by_pr_state_filters_for_sweep(db) -> None:
    _insert_proposal(skill_name="a")
    b = _insert_proposal(skill_name="b")
    backflow_store.set_pr_state(b, "backed_up")

    unbacked = backflow_store.list_by_pr_state(None, status="pending")
    backed = backflow_store.list_by_pr_state("backed_up", status="pending")

    assert {p["skill_name"] for p in unbacked} == {"a"}
    assert {p["skill_name"] for p in backed} == {"b"}


def test_defer_pr_state_does_not_clobber_already_advanced_state(db) -> None:
    """A losing concurrent sweep call must not stomp a winner's recorded progress.

    Two overlapping sweep runs can both attempt to push the same backup branch
    name; the winner records "backed_up" first, the loser's push then genuinely
    fails (non-fast-forward) and must defer without erasing the winner's state.
    """
    pid = _insert_proposal()
    backflow_store.set_pr_link(pid, branch="backflow/support/crm-ops")
    backflow_store.set_pr_state(pid, "backed_up")

    backflow_store.defer_pr_state(pid)

    proposal = backflow_store.get_proposal(pid)
    assert proposal is not None
    assert proposal["pr_state"] == "backed_up"


def test_defer_pr_state_applies_from_unbacked_or_deferred(db) -> None:
    pid = _insert_proposal()

    backflow_store.defer_pr_state(pid)
    assert backflow_store.get_proposal(pid)["pr_state"] == "deferred"

    backflow_store.defer_pr_state(pid)  # already deferred: stays deferred
    assert backflow_store.get_proposal(pid)["pr_state"] == "deferred"
