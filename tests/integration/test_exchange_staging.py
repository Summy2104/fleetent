"""Integration: /exchange staging degrade for backends without exchange_mount (§4.7/4.8).

When the backend cannot ro-mount the scope view (no `exchange_mount` capability), run_code
falls back to staging: before exec, the `/exchange/...` references in the code are
attribution-checked and the passing ones copied into the container, with a degrade log.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent import artifact_exchange
from fleetent.db import SQLiteDatabase
from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.schema_migrations import migrate
from fleetent.tools import builtin_tools


@pytest.fixture
def _exchange(tmp_path, monkeypatch):
    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, MIGRATIONS)
    monkeypatch.setattr(artifact_exchange, "_state_db", db)
    monkeypatch.setattr(artifact_exchange, "_server_roots", {})
    root = tmp_path / "exchange" / "gd" / "data"
    root.mkdir(parents=True)
    (root / "report.txt").write_text("payload")
    artifact_exchange.register_server_root("gd", root)
    return root


def _backend(*, exchange_mount: bool):
    from fleetent.integrations.sandbox.backend import BackendCapabilities

    b = MagicMock()
    b.name = "stub"
    b.capabilities = BackendCapabilities(
        persist_workspace=False,
        workspace_mount=True,
        orphan_cleanup=True,
        exchange_mount=exchange_mount,
    )
    b.stage_file = AsyncMock()
    return b


async def test_staging_copies_own_scope_refs_into_container(_exchange):
    artifact_exchange.register(server_id="gd", rel_path="report.txt", scope_key="K1")
    backend = _backend(exchange_mount=False)
    code = "open('/exchange/gd/report.txt').read()"
    staged = await builtin_tools._stage_exchange_refs(code, "K1", backend, "ws1")
    assert staged == 1
    backend.stage_file.assert_awaited_once()
    args = backend.stage_file.await_args
    assert args.args[0] == "ws1"
    assert args.args[1] == "/exchange/gd/report.txt"
    assert args.args[2] == b"payload"


async def test_staging_skips_cross_scope_refs(_exchange):
    artifact_exchange.register(server_id="gd", rel_path="report.txt", scope_key="K1")
    backend = _backend(exchange_mount=False)
    code = "open('/exchange/gd/report.txt').read()"
    staged = await builtin_tools._stage_exchange_refs(code, "K2", backend, "ws1")  # other scope
    assert staged == 0
    backend.stage_file.assert_not_awaited()


async def test_no_staging_when_backend_capable(_exchange):
    artifact_exchange.register(server_id="gd", rel_path="report.txt", scope_key="K1")
    backend = _backend(exchange_mount=True)  # mount handles it → no staging
    code = "open('/exchange/gd/report.txt').read()"
    staged = await builtin_tools._stage_exchange_refs(code, "K1", backend, "ws1")
    assert staged == 0
    backend.stage_file.assert_not_awaited()


async def test_no_refs_no_staging(_exchange):
    backend = _backend(exchange_mount=False)
    staged = await builtin_tools._stage_exchange_refs("print(1)", "K1", backend, "ws1")
    assert staged == 0
