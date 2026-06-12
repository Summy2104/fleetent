"""Unit tests: generate_image writes to per-scope workspace, returns relative ref.

(image-generation-tool / sandbox-workspace-root). Mock the image endpoint + a tmp
workspace; assert the saved file lands under the per-scope workspace `generated/` and
the returned reference is a workspace-relative `generated/<name>.png` (no base64, no
host absolute path).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.tools import builtin_tools
from fleetent.tools.registry import ToolContext


@pytest.fixture
def workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    from fleetent import paths

    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path / "ws")
    return tmp_path


async def test_generate_image_returns_relative_ref(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_generate(prompt: str, size: str | None = None) -> bytes:
        return b"\x89PNG fake bytes"

    monkeypatch.setattr(builtin_tools.image_gen_client, "generate", _fake_generate)
    ctx = ToolContext(session_id="img-sess", agent_name="bot")
    result = await builtin_tools.generate_image("a cat", tool_context=ctx)

    assert "base64" not in result
    assert "/workspace" not in result  # no container-absolute path leaks to the model
    # The reference is the workspace-relative form generated/<name>.png.
    ref = result.split(": ", 1)[1].strip()
    assert ref.startswith("generated/")
    assert ref.endswith(".png")
    assert not ref.startswith("/")  # not a host absolute path


async def test_generate_image_file_lands_in_workspace(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_generate(prompt: str, size: str | None = None) -> bytes:
        return b"PNGBYTES"

    monkeypatch.setattr(builtin_tools.image_gen_client, "generate", _fake_generate)
    from fleetent.tools.builtin_tools import _get_manager

    ctx = ToolContext(session_id="img-sess2", agent_name="bot")
    result = await builtin_tools.generate_image("a dog", tool_context=ctx)
    ref = result.split(": ", 1)[1].strip()

    mgr = _get_manager()
    root = mgr.workspace_host_path(mgr.scope, "img-sess2", "bot")
    assert (root / ref).read_bytes() == b"PNGBYTES"
