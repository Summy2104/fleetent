import os
from mini_agent import tools  # noqa: F401 — registers tools as side effect
from mini_agent import tool_registry


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
