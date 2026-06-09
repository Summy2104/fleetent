"""Unit tests: manager config-hash reuse invalidation (sandbox-hardening, task 3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from fleetent.integrations.sandbox.config import SandboxResources
from fleetent.integrations.sandbox.manager import SandboxManager, Scope


@pytest.fixture
def workspaces(monkeypatch, tmp_path):
    from fleetent import paths

    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path / "ws")
    return tmp_path


def _mgr(client) -> SandboxManager:
    return SandboxManager(
        client=client,
        scope=Scope.SESSION,
        resources_by_scope={"session": SandboxResources(), "agent": SandboxResources()},
    )


def _client(*, found: str | None, inspect_hash: str | None) -> MagicMock:
    c = MagicMock()
    c.find_workspace = AsyncMock(return_value=found)
    c.inspect_config_hash = AsyncMock(return_value=inspect_hash)
    c.destroy_workspace = AsyncMock()
    c.create_workspace = AsyncMock(return_value="cid-new")
    c.image_exists = AsyncMock(return_value=False)
    return c


async def test_stale_config_rebuilds(workspaces) -> None:
    c = _client(found="cid-old", inspect_hash="STALE")
    mgr = _mgr(c)
    ws_id = await mgr.acquire(Scope.SESSION, "sess", "bot")
    c.destroy_workspace.assert_awaited_once()
    c.create_workspace.assert_awaited_once()
    assert ws_id == "cid-new"


async def test_matching_config_reuses(workspaces) -> None:
    # First create to learn the desired hash, then re-adopt with that same hash.
    c0 = _client(found=None, inspect_hash=None)
    mgr0 = _mgr(c0)
    await mgr0.acquire(Scope.SESSION, "sess", "bot")
    desired = c0.create_workspace.await_args.kwargs["config_hash"]

    c = _client(found="cid-old", inspect_hash=desired)
    mgr = _mgr(c)
    ws_id = await mgr.acquire(Scope.SESSION, "sess", "bot")
    c.destroy_workspace.assert_not_awaited()
    c.create_workspace.assert_not_awaited()
    assert ws_id == "cid-old"


async def test_unlabeled_old_container_reused(workspaces) -> None:
    # A container with no confighash label (None) is conservatively reused, not killed.
    c = _client(found="cid-old", inspect_hash=None)
    mgr = _mgr(c)
    ws_id = await mgr.acquire(Scope.SESSION, "sess", "bot")
    c.destroy_workspace.assert_not_awaited()
    c.create_workspace.assert_not_awaited()
    assert ws_id == "cid-old"


async def test_fresh_create_labels_with_confighash(workspaces) -> None:
    c = _client(found=None, inspect_hash=None)
    mgr = _mgr(c)
    await mgr.acquire(Scope.SESSION, "sess", "bot")
    assert c.create_workspace.await_args.kwargs.get("config_hash")
