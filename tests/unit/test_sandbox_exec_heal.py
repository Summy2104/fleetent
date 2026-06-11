"""run_code self-heals when its acquired container died before exec
(sandbox-liveness-reacquire, the verify-then-die race window)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fleetent.integrations.sandbox.backend import ExecResult
from fleetent.integrations.sandbox.manager import Scope


async def test_run_code_heals_missing_container(monkeypatch) -> None:
    from fleetent.tools import builtin_tools as bt

    backend = MagicMock()
    backend.is_workspace_missing = lambda res: "No such container" in res.stderr

    manager = MagicMock()
    manager.scope = Scope.SESSION
    manager.backend = backend
    manager.resources_for.return_value = MagicMock(exec_timeout=30)
    manager.acquire = AsyncMock(side_effect=["ws-dead", "ws-new"])
    manager.invalidate = MagicMock()

    async def fake_exec_or_cancel(client, ws_id, command, token, session_id=None):
        if ws_id == "ws-dead":
            return ExecResult("", "Error response from daemon: No such container: x", 1)
        return ExecResult("healed-output\n", "", 0)

    monkeypatch.setattr(bt, "_exec_or_cancel", fake_exec_or_cancel)
    monkeypatch.setattr(bt, "_get_manager", lambda: manager)

    out = await bt.run_code("print('hi')")

    assert "healed-output" in out
    manager.invalidate.assert_called_once()
    assert manager.acquire.await_count == 2
