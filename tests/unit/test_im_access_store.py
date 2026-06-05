"""Agent-local IM approval store (JSON under the agent home `data/`)."""

from fleetent.im_gateway.access import LocalApprovalStore


def _store(home):
    return LocalApprovalStore(home / "data" / "im_approvals.json")


def test_add_pending_then_approve_then_contains(tmp_path):
    store = _store(tmp_path)
    assert store.is_approved("U_alice") is False
    store.add_pending("U_alice")
    assert store.is_approved("U_alice") is False  # pending != approved
    assert "U_alice" in store.list_pending()
    store.approve("U_alice")
    assert store.is_approved("U_alice") is True


def test_approve_moves_out_of_pending(tmp_path):
    store = _store(tmp_path)
    store.add_pending("U_bob")
    store.approve("U_bob")
    assert "U_bob" not in store.list_pending()
    assert "U_bob" in store.list_approved()


def test_survives_reload(tmp_path):
    path = tmp_path / "data" / "im_approvals.json"
    s1 = LocalApprovalStore(path)
    s1.add_pending("U_p")
    s1.approve("U_a")
    # A fresh store over the same file sees the persisted state.
    s2 = LocalApprovalStore(path)
    assert s2.is_approved("U_a") is True
    assert "U_p" in s2.list_pending()


def test_isolated_per_agent(tmp_path):
    home_a = tmp_path / "agent_a"
    home_b = tmp_path / "agent_b"
    sa = _store(home_a)
    sb = _store(home_b)
    sa.approve("U_shared")
    assert sa.is_approved("U_shared") is True
    assert sb.is_approved("U_shared") is False  # other agent's home is unaffected


def test_approve_is_idempotent(tmp_path):
    store = _store(tmp_path)
    store.approve("U_x")
    store.approve("U_x")
    assert store.list_approved().count("U_x") == 1
