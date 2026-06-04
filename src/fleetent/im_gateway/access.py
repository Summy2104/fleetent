"""Agent-local IM access: approval store, identity resolution, and access gates.

Runtime-side (not platform) IM access for a self-contained agent. The static allow
rules live in the agent home (`agent.yaml` `access` block, parsed by
:mod:`fleetent.agent_config`); dynamic approvals live in a JSON store under the agent
home `data/`. All evaluation here is local — no platform-DB read — so a standalone agent
enforces its own access without a platform database (see openspec change
``per-agent-im-access``).
"""

from __future__ import annotations

import json
from pathlib import Path

from fleetent import paths

# Default agent-local approval store path (single-agent home). Injectable: the standalone
# agent runtime points this at its own home `data/`; tests pass an explicit path.
APPROVALS_PATH = paths.data_dir() / "im_approvals.json"


class LocalApprovalStore:
    """JSON-backed per-agent IM approval store under the agent home `data/`.

    Records IM-user identities as ``pending`` (awaiting approval) or ``approved``.
    Reads and writes are file-local; no platform database is touched. Writes are atomic
    (`.tmp → replace`), mirroring :mod:`fleetent.session.manager`.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def _read(self) -> dict[str, list[str]]:
        if not self._path.exists():
            return {"pending": [], "approved": []}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return {"pending": list(raw.get("pending", [])), "approved": list(raw.get("approved", []))}

    def _write(self, state: dict[str, list[str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)

    def add_pending(self, identity: str) -> None:
        state = self._read()
        if identity not in state["pending"] and identity not in state["approved"]:
            state["pending"].append(identity)
            self._write(state)

    def approve(self, identity: str) -> None:
        state = self._read()
        if identity in state["pending"]:
            state["pending"].remove(identity)
        if identity not in state["approved"]:
            state["approved"].append(identity)
        self._write(state)

    def is_approved(self, identity: str) -> bool:
        return identity in self._read()["approved"]

    def list_approved(self) -> list[str]:
        return self._read()["approved"]

    def list_pending(self) -> list[str]:
        return self._read()["pending"]
