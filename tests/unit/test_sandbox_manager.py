"""Tests for the sandbox lifecycle manager (SB2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fleetent.integrations.sandbox.backend import BackendCapabilities
from fleetent.integrations.sandbox.config import NetworkPolicy, SandboxResources
from fleetent.integrations.sandbox.manager import (
    SandboxManager,
    Scope,
    _container_name,
    _name_key,
)


def _mock_client(
    *, persist_workspace: bool = True, workspace_mount: bool = True, orphan_cleanup: bool = True
) -> MagicMock:
    """A backend stub whose async methods + capabilities are individually configurable.

    Defaults mirror the Docker backend (all capabilities true) so existing
    behaviour assertions are unchanged; degradation tests flip a flag.
    """
    client = MagicMock()
    client.find_workspace = AsyncMock(return_value=None)
    client.create_workspace = AsyncMock(return_value="cid-new")
    client.destroy_workspace = AsyncMock(return_value=None)
    client.commit_workspace = AsyncMock(return_value=None)
    client.image_exists = AsyncMock(return_value=False)
    # sandbox-hardening: re-adopt path inspects the config-hash label; None = pre-label
    # container, conservatively reused (no rebuild), preserving prior reuse behavior.
    client.inspect_config_hash = AsyncMock(return_value=None)
    # Real (not MagicMock) capabilities so the manager's gating reads concrete bools.
    client.capabilities = BackendCapabilities(
        persist_workspace=persist_workspace,
        workspace_mount=workspace_mount,
        orphan_cleanup=orphan_cleanup,
    )
    return client


def _manager(client: MagicMock | None = None, **kwargs) -> SandboxManager:
    return SandboxManager(backend=client or _mock_client(), **kwargs)


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


# --- collision-free key derivation (sandbox-lifecycle / workspace-mount) ----


def test_name_key_short_key_is_readable_unhashed():
    """A short key passes through the sanitiser verbatim (no hash suffix), keeping
    container/workspace names human-readable for the common case."""
    assert _name_key("user-U1-chan-a") == "user-U1-chan-a"
    assert _name_key("bot") == "bot"


def test_name_key_long_same_prefix_keys_do_not_collide():
    """Two keys that share a prefix longer than the truncation budget but differ
    only in the tail MUST derive to distinct name keys (no collision)."""
    prefix = "a" * 60  # well past the 48-char legacy cap
    key_a = prefix + "-session-AAAA"
    key_b = prefix + "-session-BBBB"
    derived_a = _name_key(key_a)
    derived_b = _name_key(key_b)
    assert derived_a != derived_b


def test_name_key_long_key_within_docker_limit():
    """A long key's derived name key stays within the budget so the full container
    name (`sandbox-session-<key>`) fits Docker's 63-char limit."""
    long_key = "x" * 200
    derived = _name_key(long_key)
    # `sandbox-session-` is the longest scope prefix (16 chars).
    assert len(f"sandbox-session-{derived}") <= 63


def test_name_key_hash_suffix_is_docker_legal():
    """The hash suffix must be lowercase hex so the container name stays Docker-legal."""
    derived = _name_key("y" * 200)
    # Derived names only use [a-z0-9._-]; verify the hashed suffix has no illegal chars.
    import re as _re

    assert _re.fullmatch(r"[a-zA-Z0-9_.-]+", derived) is not None


def test_container_name_long_same_prefix_keys_distinct():
    """Container names for two long same-prefix keys differ end-to-end."""
    prefix = "z" * 60
    name_a = _container_name(Scope.SESSION, prefix + "-A")
    name_b = _container_name(Scope.SESSION, prefix + "-B")
    assert name_a != name_b
    assert name_a.startswith("sandbox-session-")
    assert len(name_a) <= 63


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
    # registry now holds the container; with the liveness probe seeing it alive,
    # a second acquire must not re-create.
    client.find_workspace = AsyncMock(return_value="cid-new")
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
    # s2 still registered (not destroyed): a live re-acquire reuses the registry entry.
    client.find_workspace = AsyncMock(return_value="cid-new")
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


async def test_sweep_idle_prunes_agent_workspaces(monkeypatch):
    """sweep_idle prunes every known agent-scope workspace dir by mtime (workspace-gc),
    keyed on the agent name — even for agents not yet idle-reclaimed."""
    from fleetent.integrations.sandbox import workspace_gc

    pruned: list[str] = []
    monkeypatch.setattr(
        workspace_gc, "gc_agent_workspace", lambda key, **kw: pruned.append(key) or 0
    )
    client = _mock_client()
    now = [1000.0]
    mgr = _manager(client, scope=Scope.AGENT, idle_hours=10.0, clock=lambda: now[0])
    await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="bot")
    now[0] = 1000.0 + 100  # still recent, not reclaimed
    await mgr.sweep_idle()
    assert "bot" in pruned


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


# --- workspace mount (sandbox-workspace-mount) -----------------------------


async def test_acquire_session_creates_workspace_dir_and_passes_path(monkeypatch, tmp_path):
    """session scope derives workspaces_dir()/<session_id>, creates it, and threads
    the host path to create_workspace."""
    from fleetent import paths

    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path)
    client = _mock_client()
    mgr = _manager(client)
    await mgr.acquire(Scope.SESSION, session_id="s1", agent_name="bot")
    _, kwargs = client.create_workspace.call_args
    assert kwargs["workspace_host_path"] == str(tmp_path / "s1")
    assert (tmp_path / "s1").is_dir()


async def test_acquire_agent_scope_workspace_uses_agent_name(monkeypatch, tmp_path):
    """agent scope keys the workspace subdir on the agent name, not the session id."""
    from fleetent import paths

    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path)
    client = _mock_client()
    mgr = _manager(client, scope=Scope.AGENT)
    await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="bot")
    _, kwargs = client.create_workspace.call_args
    assert kwargs["workspace_host_path"] == str(tmp_path / "bot")
    assert (tmp_path / "bot").is_dir()


async def test_acquire_workspace_subdir_is_sanitised(monkeypatch, tmp_path):
    """Unsafe key chars are sanitised in the workspace subdir name (same policy as
    the container name), so the path stays a single safe directory."""
    from fleetent import paths

    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path)
    client = _mock_client()
    mgr = _manager(client)
    await mgr.acquire(Scope.SESSION, session_id="user:U1/chan#a", agent_name="bot")
    _, kwargs = client.create_workspace.call_args
    assert kwargs["workspace_host_path"] == str(tmp_path / "user-U1-chan-a")
    assert (tmp_path / "user-U1-chan-a").is_dir()


# --- capability degradation (sandbox-backend-abstraction) ------------------


async def test_sweep_idle_skips_commit_when_persist_unsupported():
    """persist_workspace=False: idle reclaim destroys without committing, and warns."""
    client = _mock_client(persist_workspace=False)
    now = [1000.0]
    mgr = _manager(client, idle_hours=1.0, clock=lambda: now[0])
    await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="bot")
    now[0] = 1000.0 + 2 * 3600
    await mgr.sweep_idle()
    client.commit_workspace.assert_not_awaited()
    client.destroy_workspace.assert_awaited_once_with("cid-new")


async def test_acquire_agent_skips_image_lookup_when_persist_unsupported():
    """persist_workspace=False: agent scope never looks up a committed image."""
    client = _mock_client(persist_workspace=False)
    mgr = _manager(client, scope=Scope.AGENT)
    await mgr.acquire(Scope.AGENT, session_id="s1", agent_name="bot")
    client.image_exists.assert_not_awaited()
    _, kwargs = client.create_workspace.call_args
    assert kwargs["image"] is None


async def test_acquire_omits_host_path_when_mount_unsupported(monkeypatch, tmp_path):
    """workspace_mount=False: no host path is threaded to create_workspace."""
    from fleetent import paths

    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path)
    client = _mock_client(workspace_mount=False)
    mgr = _manager(client)
    await mgr.acquire(Scope.SESSION, session_id="s1", agent_name="bot")
    _, kwargs = client.create_workspace.call_args
    assert kwargs["workspace_host_path"] is None


# --- Dead-container self-healing (sandbox-liveness-reacquire) ---------------


async def test_acquire_reuse_recreates_when_container_dead():
    """A registry hit whose container died externally must drop the entry and create."""
    client = _mock_client()
    mgr = _manager(client)
    ws1 = await mgr.acquire(Scope.SESSION, "s1", "agent-a")
    assert ws1 == "cid-new"

    # Container killed externally (OOM / docker rm): liveness probe finds nothing.
    client.find_workspace = AsyncMock(return_value=None)
    client.create_workspace = AsyncMock(return_value="cid-new2")

    ws2 = await mgr.acquire(Scope.SESSION, "s1", "agent-a")
    assert ws2 == "cid-new2"


async def test_acquire_reuse_keeps_live_container():
    """A registry hit whose container is alive keeps being reused, no create."""
    client = _mock_client()
    mgr = _manager(client)
    ws1 = await mgr.acquire(Scope.SESSION, "s1", "agent-a")

    client.find_workspace = AsyncMock(return_value=ws1)
    client.create_workspace = AsyncMock(side_effect=AssertionError("must not create"))

    ws2 = await mgr.acquire(Scope.SESSION, "s1", "agent-a")
    assert ws2 == ws1


async def test_manager_invalidate_removes_registry_entry():
    """invalidate() drops the (scope, key) registration so next acquire recreates."""
    client = _mock_client()
    mgr = _manager(client)
    ws1 = await mgr.acquire(Scope.SESSION, "s1", "agent-a")
    assert ws1 == "cid-new"
    mgr.invalidate(Scope.SESSION, "s1", "agent-a")
    client.create_workspace = AsyncMock(return_value="cid-after-invalidate")
    ws2 = await mgr.acquire(Scope.SESSION, "s1", "agent-a")
    assert ws2 == "cid-after-invalidate"
