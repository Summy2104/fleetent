"""Unit: /exchange read-only view mount (§4.3-4.6).

The Docker backend declares the `exchange_mount` capability and bind-mounts the run's
scope view directory read-only at `/exchange`. Real-container assertions (write fails,
new links visible) require docker → covered here by asserting the `docker run` command
assembly (mock), with the live behavior left to a docker-gated environment.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fleetent.integrations.sandbox.backend import BackendCapabilities
from fleetent.integrations.sandbox.backends.docker import DockerBackend
from fleetent.integrations.sandbox.manager import SandboxManager, WorkspaceScope


def _mock_proc(returncode: int, stdout: bytes = b"cid\n") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    return proc


def test_docker_declares_exchange_mount_capability():
    assert DockerBackend().capabilities.exchange_mount is True


def test_capabilities_exchange_mount_defaults_false():
    # backends that don't opt in (and test stubs) default to no exchange mount.
    caps = BackendCapabilities(persist_workspace=True, workspace_mount=True, orphan_cleanup=True)
    assert caps.exchange_mount is False


def test_exchange_flags_assembles_ro_mount():
    flags = DockerBackend()._exchange_flags("/home/agent/exchange/.views/K1")
    assert flags == [
        "--mount",
        "type=bind,source=/home/agent/exchange/.views/K1,target=/exchange,readonly",
    ]


def test_exchange_flags_colon_in_scope_key_path_is_safe():
    # scope_key == session_id "slack:dm:U1:1781..." → view path contains colons. The old
    # `-v src:dst:ro` form produced "too many colons" and broke `docker run`. The --mount
    # form keeps the full source path intact and emits no bare `-v <colon-path>`.
    view = "/home/agent/exchange/.views/slack:dm:U1:1781443457.4"
    flags = DockerBackend()._exchange_flags(view)
    assert flags == ["--mount", f"type=bind,source={view},target=/exchange,readonly"]
    assert "-v" not in flags  # never the colon-splitting positional form


def test_exchange_flags_empty_when_no_view():
    assert DockerBackend()._exchange_flags(None) == []


async def test_create_workspace_includes_exchange_ro_mount():
    backend = DockerBackend()
    captured: dict[str, object] = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        return _mock_proc(0)

    with patch("asyncio.create_subprocess_exec", AsyncMock(side_effect=fake_exec)):
        await backend.create_workspace(
            name="sandbox-session-s1",
            workspace_host_path="/home/agent/data/workspaces/s1",
            exchange_view_path="/home/agent/exchange/.views/s1",
        )
    args = list(captured["args"])
    assert "--mount" in args
    assert "type=bind,source=/home/agent/exchange/.views/s1,target=/exchange,readonly" in args


async def test_create_workspace_omits_exchange_mount_when_absent():
    backend = DockerBackend()
    captured: dict[str, object] = {}

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        return _mock_proc(0)

    with patch("asyncio.create_subprocess_exec", AsyncMock(side_effect=fake_exec)):
        await backend.create_workspace(name="sandbox-session-s1")
    assert not any("target=/exchange" in str(a) for a in captured["args"])


async def test_manager_acquire_passes_exchange_view_when_capable(monkeypatch, tmp_path):
    """The manager threads the run's scope view dir to create_workspace on a capable backend."""
    from fleetent import artifact_exchange, paths

    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr(artifact_exchange, "_views_root", tmp_path / "exchange" / ".views")

    client = MagicMock()
    client.find_workspace = AsyncMock(return_value=None)
    client.create_workspace = AsyncMock(return_value="cid")
    client.inspect_config_hash = AsyncMock(return_value=None)
    client.image_exists = AsyncMock(return_value=False)
    client.capabilities = BackendCapabilities(
        persist_workspace=True, workspace_mount=True, orphan_cleanup=True, exchange_mount=True
    )
    mgr = SandboxManager(backend=client, scope=WorkspaceScope.SESSION)
    await mgr.acquire(WorkspaceScope.SESSION, session_id="s1", agent_name="bot")
    _, kwargs = client.create_workspace.call_args
    assert kwargs["exchange_view_path"] == str(tmp_path / "exchange" / ".views" / "s1")


async def test_manager_acquire_no_exchange_view_when_incapable(monkeypatch, tmp_path):
    from fleetent import artifact_exchange, paths

    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr(artifact_exchange, "_views_root", tmp_path / "exchange" / ".views")

    client = MagicMock()
    client.find_workspace = AsyncMock(return_value=None)
    client.create_workspace = AsyncMock(return_value="cid")
    client.inspect_config_hash = AsyncMock(return_value=None)
    client.image_exists = AsyncMock(return_value=False)
    client.capabilities = BackendCapabilities(
        persist_workspace=True, workspace_mount=True, orphan_cleanup=True, exchange_mount=False
    )
    mgr = SandboxManager(backend=client, scope=WorkspaceScope.SESSION)
    await mgr.acquire(WorkspaceScope.SESSION, session_id="s1", agent_name="bot")
    _, kwargs = client.create_workspace.call_args
    assert kwargs.get("exchange_view_path") is None
