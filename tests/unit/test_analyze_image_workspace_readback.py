"""Unit tests: analyze_image reads uploads via workspace resolution (vision-as-tool).

Inbound images save to the per-scope workspace `uploads/`; analyze_image reads them
back by the workspace-relative ref. A legacy host-absolute ref still resolves; an
invalid ref returns an error string (contract preserved) rather than raising. Vision
endpoint is mocked; tmp workspace.
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


async def test_save_then_analyze_relative_ref(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, bytes] = {}

    async def _fake_analyze(data: bytes, instruction: str) -> str:
        seen["data"] = data
        return "ok-analysis"

    monkeypatch.setattr(builtin_tools.vision_client, "analyze", _fake_analyze)
    ctx = ToolContext(session_id="vis-sess", agent_name="bot")
    ref = builtin_tools._save_upload(b"IMG", "image/png", ctx)
    assert ref.startswith("uploads/")
    assert not ref.startswith("/")

    result = await builtin_tools.analyze_image(ref, "what", tool_context=ctx)
    assert result == "ok-analysis"
    assert seen["data"] == b"IMG"


async def test_invalid_ref_returns_error_text(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = ToolContext(session_id="vis-sess2", agent_name="bot")
    result = await builtin_tools.analyze_image("uploads/missing.png", "what", tool_context=ctx)
    assert result.startswith("error:")  # no exception raised


async def test_legacy_absolute_ref_fallback(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fake_analyze(data: bytes, instruction: str) -> str:
        return f"len={len(data)}"

    monkeypatch.setattr(builtin_tools.vision_client, "analyze", _fake_analyze)
    legacy = tmp_path / "legacy.png"
    legacy.write_bytes(b"LEGACYBYTES")
    ctx = ToolContext(session_id="vis-sess3", agent_name="bot")
    result = await builtin_tools.analyze_image(str(legacy), "what", tool_context=ctx)
    assert result == "len=11"
