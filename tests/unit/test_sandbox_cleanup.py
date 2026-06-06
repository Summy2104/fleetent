"""Tests for SB8 orphan-sandbox cleanup orchestration (sandbox_cleanup)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fleetent.integrations.sandbox.cleanup import cleanup_orphans


def _client(names: list[str]) -> AsyncMock:
    client = AsyncMock()
    client.list_containers = AsyncMock(return_value=names)
    client.destroy_workspace = AsyncMock()
    return client


async def test_cleanup_orphans_destroys_each_listed_container():
    client = _client(["sandbox-session-1", "sandbox-agent-bot"])
    count = await cleanup_orphans(client)
    assert count == 2
    destroyed = {c.args[0] for c in client.destroy_workspace.await_args_list}
    assert destroyed == {"sandbox-session-1", "sandbox-agent-bot"}


async def test_cleanup_orphans_queries_with_sandbox_prefix():
    client = _client([])
    await cleanup_orphans(client)
    assert client.list_containers.await_args.args[0] == "sandbox-"


async def test_cleanup_orphans_empty_list_returns_zero():
    client = _client([])
    count = await cleanup_orphans(client)
    assert count == 0
    client.destroy_workspace.assert_not_awaited()


async def test_cleanup_orphans_docker_unavailable_returns_zero():
    """Docker unavailable surfaces as an empty list from list_containers -> 0."""
    client = _client([])
    count = await cleanup_orphans(client)
    assert count == 0


async def test_cleanup_orphans_skips_names_without_prefix():
    """D3: Docker --filter name= is substring matching, so a container whose name
    merely contains 'sandbox-' mid-string must not be destroyed."""
    client = _client(["sandbox-session-1", "my-sandbox-backup", "not-related"])
    count = await cleanup_orphans(client)
    assert count == 1
    destroyed = {c.args[0] for c in client.destroy_workspace.await_args_list}
    assert destroyed == {"sandbox-session-1"}


async def test_cleanup_orphans_logs_count_and_names():
    """D4 audit: the count and the destroyed container names are logged."""
    from unittest.mock import patch

    client = _client(["sandbox-session-1", "sandbox-agent-bot"])
    with patch("fleetent.integrations.sandbox.cleanup._logger") as mock_log:
        await cleanup_orphans(client)
    mock_log.info.assert_called_once()
    kw = mock_log.info.call_args.kwargs
    assert kw["count"] == 2
    assert "sandbox-session-1" in kw["destroyed"]
    assert "sandbox-agent-bot" in kw["destroyed"]


async def test_cleanup_orphans_callable_standalone_returns_count():
    """The orchestration entry point is callable without server/lifespan/scheduler."""
    client = _client(["sandbox-session-1"])
    count = await cleanup_orphans(client)
    assert count == 1
