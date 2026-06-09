"""Unit tests for the container file IO backend (file-tools-sandbox-execution, Task 3+).

The container backend turns file ops into shell commands run via client.exec, locked
to /workspace. Here client.exec is a canned fake keyed on a command marker — no real
docker — so we verify command dispatch, base64 decoding and output parsing.
"""

from __future__ import annotations

import base64

from fleetent.integrations.sandbox.client import ExecResult
from fleetent.tools import file_tools


class _CannedClient:
    """Fake SandboxClient.exec returning a canned result per command marker."""

    def __init__(self, by_marker: dict[str, ExecResult]) -> None:
        self.by_marker = by_marker
        self.commands: list[str] = []

    async def exec(self, ws_id: str, command: str, session_id: str | None = None) -> ExecResult:
        self.commands.append(command)
        for marker, res in self.by_marker.items():
            if marker in command:
                return res
        return ExecResult(stdout="", stderr="no match", exit_code=1)


def _backend(client: _CannedClient) -> file_tools._ContainerBackend:
    return file_tools._ContainerBackend(client=client, ws_id="ws-1", session_id="s")


async def test_container_probe_file() -> None:
    backend = _backend(_CannedClient({"[ -d": ExecResult("file 11\n", "", 0)}))
    stat = await backend.probe("a.txt")
    assert stat.kind == "file"
    assert stat.size == 11


async def test_container_probe_dir() -> None:
    backend = _backend(_CannedClient({"[ -d": ExecResult("dir\n", "", 0)}))
    stat = await backend.probe("sub")
    assert stat.kind == "dir"


async def test_container_probe_missing() -> None:
    backend = _backend(_CannedClient({"[ -d": ExecResult("missing\n", "", 0)}))
    stat = await backend.probe("nope.txt")
    assert stat.kind == "missing"


async def test_container_read_bytes_decodes_base64() -> None:
    raw = b"hello\nworld\n"
    encoded = base64.b64encode(raw).decode() + "\n"
    backend = _backend(_CannedClient({"base64": ExecResult(encoded, "", 0)}))
    assert await backend.read_bytes("a.txt") == raw


async def test_container_list_dir_parses_find_output() -> None:
    out = "a.py\tf\t5\t1700000000.0\nsub\td\t0\t1700000001.5\n"
    backend = _backend(_CannedClient({"-printf": ExecResult(out, "", 0)}))
    entries = await backend.list_dir(".")
    by_name = {e.name: e for e in entries}
    assert set(by_name) == {"a.py", "sub"}
    assert by_name["sub"].is_dir is True
    assert by_name["a.py"].is_dir is False
    assert by_name["a.py"].size == 5


async def test_container_read_escape_rejected() -> None:
    backend = _backend(_CannedClient({}))
    import pytest

    with pytest.raises(ValueError):
        await backend.probe("../etc/passwd")
