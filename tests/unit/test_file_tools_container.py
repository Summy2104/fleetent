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


# ── container search (Task 6) ─────────────────────────────────────────────────


async def test_container_search_content_finds_matches() -> None:
    out = "/workspace/a.py:1:def foo():\n"
    backend = _backend(_CannedClient({"grep": ExecResult(out, "", 0)}))
    result = await backend.search_content("def foo", ".", "", 100)
    assert "a.py" in result
    assert "def foo" in result


async def test_container_search_content_no_match() -> None:
    backend = _backend(_CannedClient({"grep": ExecResult("", "", 1)}))
    result = await backend.search_content("nope", ".", "", 100)
    assert "无匹配" in result


async def test_container_search_content_error() -> None:
    backend = _backend(_CannedClient({"grep": ExecResult("", "grep: bad regex", 2)}))
    result = await backend.search_content("[bad", ".", "", 100)
    assert "error" in result.lower()


async def test_container_search_content_escape_rejected() -> None:
    backend = _backend(_CannedClient({}))
    import pytest

    with pytest.raises(ValueError):
        await backend.search_content("x", "../etc", "", 100)


async def test_container_search_files_lists_matches() -> None:
    out = "/workspace/new.py\n/workspace/old.py\n"
    backend = _backend(_CannedClient({"find": ExecResult(out, "", 0)}))
    result = await backend.search_files("*.py", ".", 100)
    assert "new.py" in result


async def test_container_search_files_truncates() -> None:
    out = "".join(f"/workspace/f{i}.py\n" for i in range(20))
    backend = _backend(_CannedClient({"find": ExecResult(out, "", 0)}))
    result = await backend.search_files("*.py", ".", 5)
    assert "截断" in result


# --- exec self-healing on missing container (sandbox-liveness-reacquire) ----


class _DyingThenHealthyClient:
    """exec hits container-missing on the dead ws id, succeeds on the healed one."""

    def __init__(self) -> None:
        self.ws_seen: list[str] = []

    async def exec(
        self, ws_id: str, command: str, session_id: str | None = None, stdin: bytes | None = None
    ) -> ExecResult:
        self.ws_seen.append(ws_id)
        if ws_id == "ws-dead":
            return ExecResult("", "Error response from daemon: No such container: ws-dead", 1)
        return ExecResult("file 11\n", "", 0)

    def is_workspace_missing(self, res: ExecResult) -> bool:
        return "No such container" in res.stderr


async def test_container_exec_heals_missing_container() -> None:
    from unittest.mock import AsyncMock, MagicMock

    client = _DyingThenHealthyClient()
    manager = MagicMock()
    manager.backend = client
    manager.invalidate = MagicMock()
    manager.acquire = AsyncMock(return_value="ws-new")

    backend = file_tools._ContainerBackend(
        client=client, ws_id="ws-dead", session_id="s", manager=manager, agent_name="bot"
    )
    stat = await backend.probe("a.txt")

    assert stat.kind == "file"
    manager.invalidate.assert_called_once()
    assert client.ws_seen == ["ws-dead", "ws-new"]


# --- infrastructure failures must not masquerade as path status --------------


def _dead_client(marker: str) -> _CannedClient:
    client = _CannedClient(
        {marker: ExecResult("", "Error response from daemon: No such container: x", 1)}
    )
    client.is_workspace_missing = lambda res: "No such container" in res.stderr  # type: ignore[attr-defined]
    return client


async def test_container_probe_raises_on_infra_failure() -> None:
    import pytest

    backend = _backend(_dead_client("[ -d"))
    with pytest.raises(file_tools._BackendError) as ei:
        await backend.probe("a.txt")
    assert "沙箱" in str(ei.value)


async def test_container_search_files_reports_infra_failure() -> None:
    backend = _backend(_dead_client("-name"))
    out = await backend.search_files("*.xlsx", ".", 50)
    assert "沙箱" in out
    assert "无匹配" not in out


async def test_container_list_dir_raises_on_infra_failure() -> None:
    import pytest

    backend = _backend(_dead_client("-printf"))
    with pytest.raises(file_tools._BackendError):
        await backend.list_dir(".")
