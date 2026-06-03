"""TUI gateway approve → permission_gate.resolve (tui-gateway 4.5, v1 scope).

v1 only implements approval *resolution* over WS; the `approval_required` push during
streaming is descoped (run_stream does not gate approvals) — see the follow-on change
`streaming-approval-gating`.
"""

from typing import Any

from fleetent.tui import dispatch as d
from fleetent.tui import protocol as p


class FakeTransport:
    async def write(self, obj: dict[str, Any]) -> bool:
        return True

    async def close(self) -> None:
        pass


class FakeGate:
    def __init__(self, found: bool = True) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self._found = found

    async def resolve(self, approval_id: str, decision: str, approver_user_id: str) -> bool:
        self.calls.append((approval_id, decision, approver_user_id))
        return self._found


def _conn() -> d.Connection:
    return d.Connection(user_id="u1", transport=FakeTransport())


async def test_approve_approved_routes_to_gate(monkeypatch):
    gate = FakeGate(found=True)
    monkeypatch.setattr(d.permission_gate, "_default_gate", gate)
    conn = _conn()
    resp = await d.dispatch(
        conn,
        {"id": 1, "method": "approve", "params": {"approval_id": "a1", "decision": "approved"}},
    )
    assert resp["result"] == {"ok": True}
    assert gate.calls == [("a1", "approved", "u1")]  # routed with this connection's user


async def test_approve_rejected_routes_to_gate(monkeypatch):
    gate = FakeGate(found=True)
    monkeypatch.setattr(d.permission_gate, "_default_gate", gate)
    conn = _conn()
    resp = await d.dispatch(
        conn,
        {"id": 2, "method": "approve", "params": {"approval_id": "a2", "decision": "rejected"}},
    )
    assert resp["result"] == {"ok": True}
    assert gate.calls[0][1] == "rejected"


async def test_approve_unknown_approval_returns_ok_false(monkeypatch):
    gate = FakeGate(found=False)  # gate.resolve returns False for unknown/expired
    monkeypatch.setattr(d.permission_gate, "_default_gate", gate)
    resp = await d.dispatch(
        _conn(),
        {"id": 3, "method": "approve", "params": {"approval_id": "x", "decision": "approved"}},
    )
    assert resp["result"] == {"ok": False}


async def test_approve_invalid_decision_is_invalid_params(monkeypatch):
    gate = FakeGate()
    monkeypatch.setattr(d.permission_gate, "_default_gate", gate)
    resp = await d.dispatch(
        _conn(), {"id": 4, "method": "approve", "params": {"approval_id": "a", "decision": "maybe"}}
    )
    assert resp["error"]["code"] == p.INVALID_PARAMS
    assert gate.calls == []  # never reached the gate
