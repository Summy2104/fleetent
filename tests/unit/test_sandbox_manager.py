"""Tests for the sandbox lifecycle manager (SB2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fleetent.sandbox_config import NetworkPolicy, SandboxResources
from fleetent.sandbox_manager import SandboxManager, Scope


def _mock_client() -> MagicMock:
    """A SandboxClient stub whose async methods are individually configurable."""
    client = MagicMock()
    client.find_workspace = AsyncMock(return_value=None)
    client.create_workspace = AsyncMock(return_value="cid-new")
    client.destroy_workspace = AsyncMock(return_value=None)
    client.commit_workspace = AsyncMock(return_value=None)
    client.image_exists = AsyncMock(return_value=False)
    return client


def _manager(client: MagicMock | None = None, **kwargs) -> SandboxManager:
    return SandboxManager(client=client or _mock_client(), **kwargs)


# --- Section 3: Scope + construction ---------------------------------------


def test_scope_values():
    assert Scope.SESSION == "session"
    assert Scope.AGENT == "agent"


def test_manager_construction_defaults():
    """A manager can be built with just a client; scope/idle_hours have defaults."""
    mgr = _manager()
    assert mgr.scope in (Scope.SESSION, Scope.AGENT)
    assert mgr.idle_hours > 0


def test_manager_construction_injectable():
    res = {Scope.SESSION: SandboxResources(), Scope.AGENT: SandboxResources(read_only=False)}
    mgr = _manager(scope=Scope.AGENT, idle_hours=5.0, resources_by_scope=res)
    assert mgr.scope is Scope.AGENT
    assert mgr.idle_hours == 5.0
    assert mgr.resources_for(Scope.AGENT).read_only is False


# --- Section 4: acquire (naming / create / reuse) --------------------------


async def test_acquire_session_name_and_hardened_tier():
    client = _mock_client()
    mgr = _manager(client)
    await mgr.acquire(Scope.SESSION, session_id="user:U1/chan#a", agent_name="bot")
    _, kwargs = client.create_workspace.call_args
    assert kwargs["name"] == "sandbox-session-user-U1-chan-a"
    assert kwargs["resources"].read_only is True
    assert kwargs["resources"].network is NetworkPolicy.NONE


async def test_acquire_agent_name_and_downgraded_tier():
    client = _mock_client()
    agent_tier = SandboxResources(read_only=False, network=NetworkPolicy.ALLOW_ALL)
    mgr = _manager(
        client,
        resources_by_scope={Scope.SESSION: SandboxResources(), Scope.AGENT: agent_tier},
    )
    await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="my:agent/x")
    _, kwargs = client.create_workspace.call_args
    assert kwargs["name"] == "sandbox-agent-my-agent-x"
    assert kwargs["resources"].read_only is False
    assert kwargs["resources"].network is NetworkPolicy.ALLOW_ALL


async def test_acquire_first_time_creates():
    client = _mock_client()
    mgr = _manager(client)
    ws = await mgr.acquire(Scope.SESSION, session_id="s1", agent_name="bot")
    assert ws == "cid-new"
    client.create_workspace.assert_awaited_once()
    client.find_workspace.assert_awaited_once()


async def test_acquire_reuses_existing_without_create():
    client = _mock_client()
    client.find_workspace = AsyncMock(return_value="cid-existing")
    mgr = _manager(client)
    ws = await mgr.acquire(Scope.SESSION, session_id="s1", agent_name="bot")
    assert ws == "cid-existing"
    client.create_workspace.assert_not_awaited()


async def test_acquire_second_call_same_key_reuses_registry():
    client = _mock_client()
    mgr = _manager(client)
    await mgr.acquire(Scope.SESSION, session_id="s1", agent_name="bot")
    # registry now holds the container; a second acquire must not re-create.
    await mgr.acquire(Scope.SESSION, session_id="s1", agent_name="bot")
    assert client.create_workspace.await_count == 1


async def test_acquire_different_keys_isolated():
    client = _mock_client()
    created: list[str] = []

    async def fake_create(**kwargs):
        created.append(kwargs["name"])
        return f"cid-{len(created)}"

    client.create_workspace = AsyncMock(side_effect=fake_create)
    mgr = _manager(client)
    await mgr.acquire(Scope.SESSION, session_id="s1", agent_name="bot")
    await mgr.acquire(Scope.SESSION, session_id="s2", agent_name="bot")
    assert created == ["sandbox-session-s1", "sandbox-session-s2"]


# --- Section 5: release_session / sweep_idle -------------------------------


async def test_release_session_destroys_only_that_session():
    client = _mock_client()
    mgr = _manager(client)
    await mgr.acquire(Scope.SESSION, session_id="s1", agent_name="bot")
    await mgr.acquire(Scope.SESSION, session_id="s2", agent_name="bot")
    await mgr.release_session("s1")
    client.destroy_workspace.assert_awaited_once_with("cid-new")
    # s2 still registered (not destroyed): a re-acquire reuses the registry entry.
    client.create_workspace.reset_mock()
    await mgr.acquire(Scope.SESSION, session_id="s2", agent_name="bot")
    client.create_workspace.assert_not_awaited()


async def test_release_session_ignores_agent_scope():
    client = _mock_client()
    mgr = _manager(client, scope=Scope.AGENT)
    await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="bot")
    await mgr.release_session("s1")
    client.destroy_workspace.assert_not_awaited()


async def test_sweep_idle_commits_then_destroys_idle_agent():
    client = _mock_client()
    now = [1000.0]
    mgr = _manager(client, idle_hours=1.0, clock=lambda: now[0])
    await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="bot")
    now[0] = 1000.0 + 2 * 3600  # 2h later, > idle_hours
    await mgr.sweep_idle()
    client.commit_workspace.assert_awaited_once()
    client.destroy_workspace.assert_awaited_once_with("cid-new")
    # commit before destroy
    assert client.commit_workspace.await_args.args[0] == "cid-new"


async def test_sweep_idle_skips_recent_agent():
    client = _mock_client()
    now = [1000.0]
    mgr = _manager(client, idle_hours=2.0, clock=lambda: now[0])
    await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="bot")
    now[0] = 1000.0 + 1800  # 30 min later, < idle_hours
    await mgr.sweep_idle()
    client.destroy_workspace.assert_not_awaited()


async def test_sweep_idle_ignores_session_scope():
    client = _mock_client()
    now = [1000.0]
    mgr = _manager(client, scope=Scope.SESSION, idle_hours=1.0, clock=lambda: now[0])
    await mgr.acquire(Scope.SESSION, session_id="s1", agent_name="bot")
    now[0] = 1000.0 + 10 * 3600
    await mgr.sweep_idle()
    client.commit_workspace.assert_not_awaited()
    client.destroy_workspace.assert_not_awaited()


# --- Section 6: agent dependency固化 + image reuse -------------------------


async def test_sweep_idle_commits_agent_image_tag():
    client = _mock_client()
    now = [0.0]
    mgr = _manager(client, idle_hours=1.0, clock=lambda: now[0])
    await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="bot")
    now[0] = 10 * 3600
    await mgr.sweep_idle()
    tag = client.commit_workspace.await_args.args[1]
    assert tag == "fleetent-sandbox-agent-bot:latest"


async def test_acquire_agent_uses_committed_image_when_present():
    """If the committed image exists, the next acquire boots from it."""
    client = _mock_client()
    client.image_exists = AsyncMock(return_value=True)
    mgr = _manager(client)
    await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="bot")
    _, kwargs = client.create_workspace.call_args
    assert kwargs["image"] == "fleetent-sandbox-agent-bot:latest"


async def test_acquire_agent_falls_back_to_default_image_when_absent():
    client = _mock_client()
    client.image_exists = AsyncMock(return_value=False)
    mgr = _manager(client)
    await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="bot")
    _, kwargs = client.create_workspace.call_args
    assert kwargs["image"] is None


# --- SB5: env passthrough ---------------------------------------------------


async def test_acquire_passes_env_to_create_workspace():
    """acquire threads an optional `env` mapping to create_workspace (SB5)."""
    client = _mock_client()
    mgr = _manager(client)
    await mgr.acquire(Scope.SESSION, "s1", "bot", env={"DATA_DIR": "/x"})
    _, kwargs = client.create_workspace.call_args
    assert kwargs["env"] == {"DATA_DIR": "/x"}


async def test_acquire_env_defaults_to_none():
    """Omitting env keeps SB2's behaviour: create_workspace receives env=None."""
    client = _mock_client()
    mgr = _manager(client)
    await mgr.acquire(Scope.SESSION, "s1", "bot")
    _, kwargs = client.create_workspace.call_args
    assert kwargs["env"] is None
