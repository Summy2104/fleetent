import pytest

from mini_agent import (
    tool_registry,
    tools,  # noqa: F401 — registers tools as side effect
)


def test_get_current_time_registered():
    assert "get_current_time" in tool_registry._registry


def test_get_current_time_returns_utc_string():
    result = tool_registry.dispatch("get_current_time", "{}")
    assert "UTC" in result
    assert len(result) > 10


def test_calculate_basic_arithmetic():
    assert tool_registry.dispatch("calculate", '{"expression": "2 + 3"}') == "5"
    assert tool_registry.dispatch("calculate", '{"expression": "10 / 4"}') == "2.5"
    assert tool_registry.dispatch("calculate", '{"expression": "3 * 7"}') == "21"


def test_calculate_rejects_unsafe_input():
    result = tool_registry.dispatch("calculate", '{"expression": "__import__(\'os\')"}')
    assert result.startswith("error:")


def test_calculate_invalid_expression():
    result = tool_registry.dispatch("calculate", '{"expression": "1 +"}')
    assert result.startswith("error:")


def test_read_file_returns_contents(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("hello world")
    result = tool_registry.dispatch("read_file", f'{{"path": "{f}"}}')
    assert result == "hello world"


def test_read_file_truncates_at_2000_chars(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("x" * 5000)
    result = tool_registry.dispatch("read_file", f'{{"path": "{f}"}}')
    assert len(result) == 2000


def test_read_file_missing_file():
    result = tool_registry.dispatch("read_file", '{"path": "/nonexistent/path/file.txt"}')
    assert result.startswith("error:")


# ── run_code ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_code_returns_stdout(monkeypatch):
    from unittest.mock import AsyncMock
    from mini_agent.sandbox_client import ExecResult
    import mini_agent.tools as tl

    mock_client = AsyncMock()
    mock_client.create_workspace = AsyncMock(return_value="cid-123")
    mock_client.exec = AsyncMock(return_value=ExecResult(stdout="42\n", stderr="", exit_code=0))
    mock_client.destroy_workspace = AsyncMock()

    monkeypatch.setattr(tl, "SandboxClient", lambda **kw: mock_client)

    result = await tl.run_code(code="print(6 * 7)")
    assert result == "42"
    mock_client.destroy_workspace.assert_called_once_with("cid-123")


@pytest.mark.asyncio
async def test_run_code_includes_stderr(monkeypatch):
    from unittest.mock import AsyncMock
    from mini_agent.sandbox_client import ExecResult
    import mini_agent.tools as tl

    mock_client = AsyncMock()
    mock_client.create_workspace = AsyncMock(return_value="cid-456")
    mock_client.exec = AsyncMock(
        return_value=ExecResult(stdout="", stderr="NameError: name 'x' is not defined", exit_code=1)
    )
    mock_client.destroy_workspace = AsyncMock()

    monkeypatch.setattr(tl, "SandboxClient", lambda **kw: mock_client)

    result = await tl.run_code(code="print(x)")
    assert "[stderr]" in result
    assert "NameError" in result
    assert "[exit 1]" in result


@pytest.mark.asyncio
async def test_run_code_destroys_workspace_on_error(monkeypatch):
    """destroy_workspace must be called even when exec raises."""
    from unittest.mock import AsyncMock
    import mini_agent.tools as tl

    mock_client = AsyncMock()
    mock_client.create_workspace = AsyncMock(return_value="cid-789")
    mock_client.exec = AsyncMock(side_effect=RuntimeError("docker died"))
    mock_client.destroy_workspace = AsyncMock()

    monkeypatch.setattr(tl, "SandboxClient", lambda **kw: mock_client)

    with pytest.raises(RuntimeError):
        await tl.run_code(code="print('hi')")

    mock_client.destroy_workspace.assert_called_once_with("cid-789")
