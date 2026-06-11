"""Tests for the microsandbox backend (microsandbox-backend).

The SDK is mocked throughout — no real microVM / KVM is required. We inject a fake
``microsandbox`` module via ``sys.modules`` (the backend lazy-imports it inside each
method) rather than patching attributes on the real native pyo3 classes — the latter
is platform-dependent (immutable extension types) and would be fragile across wheels.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

from fleetent.integrations.sandbox.backend import BaseSandboxBackend
from fleetent.integrations.sandbox.backends.microsandbox import MicrosandboxBackend
from fleetent.integrations.sandbox.config import NetworkPolicy, SandboxResources


def _exec_output(stdout: str = "", stderr: str = "", exit_code: int = 0) -> MagicMock:
    out = MagicMock()
    out.stdout_text = stdout
    out.stderr_text = stderr
    out.exit_code = exit_code
    return out


def _fake_handle(exec_output: MagicMock | None = None) -> MagicMock:
    sb = MagicMock()
    sb.exec = AsyncMock(return_value=exec_output or _exec_output())
    sb.stop = AsyncMock()
    return sb


def _fake_msb(
    *,
    is_installed: bool = True,
    handle: MagicMock | None = None,
    none_obj: object | None = None,
    allow_obj: object | None = None,
    public_obj: object | None = None,
    bind_obj: object | None = None,
    list_return: list | None = None,
) -> types.ModuleType:
    """Build a fake `microsandbox` module to inject via sys.modules."""
    m = types.ModuleType("microsandbox")
    m.is_installed = MagicMock(return_value=is_installed)  # type: ignore[attr-defined]
    sandbox = MagicMock()
    sandbox.create = AsyncMock(return_value=handle or _fake_handle())
    sandbox.get = AsyncMock(return_value=handle or _fake_handle())
    sandbox.remove = AsyncMock()
    sandbox.list = AsyncMock(return_value=list_return or [])
    m.Sandbox = sandbox  # type: ignore[attr-defined]
    network = MagicMock()
    network.none = MagicMock(return_value=none_obj if none_obj is not None else object())
    network.allow_all = MagicMock(return_value=allow_obj if allow_obj is not None else object())
    network.public_only = MagicMock(return_value=public_obj if public_obj is not None else object())
    m.Network = network  # type: ignore[attr-defined]
    volume = MagicMock()
    volume.bind = MagicMock(return_value=bind_obj if bind_obj is not None else object())
    m.Volume = volume  # type: ignore[attr-defined]
    return m


def _inject(fake: types.ModuleType):
    return patch.dict(sys.modules, {"microsandbox": fake})


def test_subclasses_abstraction_and_capabilities() -> None:
    assert issubclass(MicrosandboxBackend, BaseSandboxBackend)
    assert MicrosandboxBackend.name == "microsandbox"
    caps = MicrosandboxBackend.capabilities
    assert caps.persist_workspace is False
    assert caps.workspace_mount is True
    assert caps.orphan_cleanup is True


async def test_available_reflects_is_installed() -> None:
    backend = MicrosandboxBackend()
    with _inject(_fake_msb(is_installed=True)):
        assert await backend.available() is True
    with _inject(_fake_msb(is_installed=False)):
        assert await backend.available() is False


async def test_available_false_on_probe_error() -> None:
    backend = MicrosandboxBackend()
    fake = _fake_msb()
    fake.is_installed = MagicMock(side_effect=RuntimeError("no kvm"))  # type: ignore[attr-defined]
    with _inject(fake):
        assert await backend.available() is False


async def test_available_false_when_package_missing() -> None:
    """If the microsandbox package cannot be imported, available() degrades to False."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "microsandbox":
            raise ImportError("no microsandbox")
        return real_import(name, *a, **k)

    backend = MicrosandboxBackend()
    with patch("builtins.__import__", side_effect=fake_import):
        assert await backend.available() is False


async def test_create_maps_name_image_cpus_memory() -> None:
    backend = MicrosandboxBackend()
    fake = _fake_msb()
    with _inject(fake):
        ws = await backend.create_workspace(
            "sandbox-session-1",
            resources=SandboxResources(memory=512, cpus=2.0),
            image="python:3.12",
        )
    assert ws == "sandbox-session-1"
    kwargs = fake.Sandbox.create.call_args.kwargs
    assert kwargs["image"] == "python:3.12"
    assert kwargs["memory"] == 512
    assert kwargs["cpus"] == 2  # float cpus coerced to int


async def test_hardening_fields_are_ignored() -> None:
    backend = MicrosandboxBackend()
    fake = _fake_msb()
    res = SandboxResources(pids_limit=128, cap_drop_all=True, run_as_user="65534:65534")
    with _inject(fake):
        await backend.create_workspace("sandbox-session-2", resources=res)
    kwargs = fake.Sandbox.create.call_args.kwargs
    assert "pids_limit" not in kwargs
    assert "cap_drop_all" not in kwargs
    assert "run_as_user" not in kwargs


async def test_network_policy_maps_to_sdk_presets() -> None:
    backend = MicrosandboxBackend()
    none_obj = object()
    fake = _fake_msb(none_obj=none_obj)
    with _inject(fake):
        await backend.create_workspace("s", resources=SandboxResources(network=NetworkPolicy.NONE))
    fake.Network.none.assert_called_once()
    assert fake.Sandbox.create.call_args.kwargs["network"] is none_obj


async def test_exec_passes_command_and_stdin() -> None:
    backend = MicrosandboxBackend()
    handle = _fake_handle(_exec_output(stdout="hi\n", exit_code=0))
    fake = _fake_msb(handle=handle)
    with _inject(fake):
        await backend.create_workspace("ws", resources=SandboxResources())
        res = await backend.exec("ws", "echo hi", stdin=b"payload")
    assert res.stdout == "hi\n"
    assert res.exit_code == 0
    args, kwargs = handle.exec.call_args
    assert args[0] == "sh"
    assert args[1] == ["-c", "echo hi"]
    assert kwargs["stdin"] == b"payload"


async def test_env_sensitive_names_filtered() -> None:
    backend = MicrosandboxBackend()
    handle = _fake_handle()
    fake = _fake_msb(handle=handle)
    with _inject(fake):
        await backend.create_workspace(
            "ws", resources=SandboxResources(), env={"SAFE": "1", "AWS_SECRET_ACCESS_KEY": "x"}
        )
        await backend.exec("ws", "env")
    passed_env = handle.exec.call_args.kwargs["env"]
    assert passed_env == {"SAFE": "1"}


async def test_workspace_bind_mount_with_readonly() -> None:
    backend = MicrosandboxBackend()
    bind_obj = object()
    fake = _fake_msb(bind_obj=bind_obj)
    with _inject(fake):
        await backend.create_workspace(
            "ws",
            resources=SandboxResources(read_only=True),
            workspace_host_path="/host/ws",
        )
    fake.Volume.bind.assert_called_once()
    assert fake.Volume.bind.call_args.args[0] == "/host/ws"
    assert fake.Volume.bind.call_args.kwargs["readonly"] is True
    assert fake.Sandbox.create.call_args.kwargs["volumes"] == {"/workspace": bind_obj}


async def test_destroy_is_idempotent() -> None:
    backend = MicrosandboxBackend()
    fake = _fake_msb()
    fake.Sandbox.remove = AsyncMock(side_effect=Exception("not found"))
    with _inject(fake):
        await backend.destroy_workspace("ws")  # must not raise


async def test_kill_calls_stop() -> None:
    backend = MicrosandboxBackend()
    handle = _fake_handle()
    fake = _fake_msb(handle=handle)
    with _inject(fake):
        await backend.create_workspace("ws", resources=SandboxResources())
        await backend.kill_workspace("ws")
    handle.stop.assert_awaited()


async def test_list_workspaces_filters_by_prefix() -> None:
    backend = MicrosandboxBackend()
    s1, s2, s3 = MagicMock(), MagicMock(), MagicMock()
    s1.name = "sandbox-session-1"
    s2.name = "sandbox-agent-bot"
    s3.name = "unrelated"
    fake = _fake_msb(list_return=[s1, s2, s3])
    with _inject(fake):
        names = await backend.list_workspaces("sandbox-")
    assert set(names) == {"sandbox-session-1", "sandbox-agent-bot"}


async def test_list_workspaces_empty_on_error() -> None:
    backend = MicrosandboxBackend()
    fake = _fake_msb()
    fake.Sandbox.list = AsyncMock(side_effect=RuntimeError("down"))
    with _inject(fake):
        assert await backend.list_workspaces("sandbox-") == []


async def test_inspect_config_hash_always_none() -> None:
    backend = MicrosandboxBackend()
    assert await backend.inspect_config_hash("ws") is None
