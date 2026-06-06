"""Tests for the enhanced schema builder (tool-schema-builder spec)."""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fleetent.tools.schema_builder import build_schema


# ── list[T] support ──────────────────────────────────────────────────────────


def test_list_str_generates_array_schema():
    def fn(items: list[str]) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    prop = schema["function"]["parameters"]["properties"]["items"]
    assert prop == {"type": "array", "items": {"type": "string"}}
    assert "items" in schema["function"]["parameters"]["required"]


def test_list_int_generates_array_of_integer():
    def fn(counts: list[int]) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    prop = schema["function"]["parameters"]["properties"]["counts"]
    assert prop == {"type": "array", "items": {"type": "integer"}}


def test_list_bool_generates_array_of_boolean():
    def fn(flags: list[bool]) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    prop = schema["function"]["parameters"]["properties"]["flags"]
    assert prop == {"type": "array", "items": {"type": "boolean"}}


# ── Optional[T] / T | None support ───────────────────────────────────────────


def test_optional_str_not_in_required():
    def fn(note: Optional[str] = None) -> str:  # noqa: UP007
        """Test."""
        return ""

    schema = build_schema(fn)
    params = schema["function"]["parameters"]
    assert "note" in params["properties"]
    assert params["properties"]["note"]["type"] == "string"
    assert "note" not in params["required"]


def test_union_none_not_in_required():
    def fn(tag: str | None = None) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    params = schema["function"]["parameters"]
    assert params["properties"]["tag"]["type"] == "string"
    assert "tag" not in params["required"]


def test_required_param_in_required_list():
    def fn(path: str) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    assert "path" in schema["function"]["parameters"]["required"]


def test_param_with_default_not_required():
    def fn(limit: int = 200) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    assert "limit" not in schema["function"]["parameters"]["required"]
    assert schema["function"]["parameters"]["properties"]["limit"]["type"] == "integer"


# ── Literal enum support ──────────────────────────────────────────────────────


def test_literal_str_generates_enum():
    def fn(action: Literal["set", "get", "clear"]) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    prop = schema["function"]["parameters"]["properties"]["action"]
    assert prop == {"type": "string", "enum": ["set", "get", "clear"]}
    assert "action" in schema["function"]["parameters"]["required"]


def test_literal_single_value():
    def fn(mode: Literal["markdown"]) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    prop = schema["function"]["parameters"]["properties"]["mode"]
    assert prop["enum"] == ["markdown"]


# ── Annotated description support ────────────────────────────────────────────


def test_annotated_adds_description():
    def fn(command: Annotated[str, "要执行的 Shell 命令"]) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    prop = schema["function"]["parameters"]["properties"]["command"]
    assert prop["type"] == "string"
    assert prop["description"] == "要执行的 Shell 命令"


def test_annotated_required_param_in_required():
    def fn(query: Annotated[str, "搜索关键词"]) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    assert "query" in schema["function"]["parameters"]["required"]


def test_unannotated_param_has_no_description():
    def fn(path: str) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    prop = schema["function"]["parameters"]["properties"]["path"]
    assert "description" not in prop


# ── out-of-band param filtering ───────────────────────────────────────────────


def test_cancel_token_excluded_from_schema():
    def fn(x: str, cancel_token=None) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    params = schema["function"]["parameters"]
    assert "cancel_token" not in params["properties"]
    assert "cancel_token" not in params.get("required", [])
    assert "x" in params["properties"]


def test_tool_context_excluded_from_schema():
    def fn(x: str, tool_context=None) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    params = schema["function"]["parameters"]
    assert "tool_context" not in params["properties"]
    assert "x" in params["properties"]


def test_client_excluded_from_schema():
    def fn(query: str, *, client) -> str:
        """Test."""
        return ""

    schema = build_schema(fn)
    params = schema["function"]["parameters"]
    assert "client" not in params["properties"]
    assert "query" in params["properties"]


# ── schema envelope ───────────────────────────────────────────────────────────


def test_schema_envelope_format():
    def fn(x: str) -> str:
        """Do something useful."""
        return ""

    schema = build_schema(fn)
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "fn"
    assert schema["function"]["description"] == "Do something useful."


def test_schema_description_uses_first_docstring_line():
    def fn(x: str) -> str:
        """First line.

        Second line ignored.
        """
        return ""

    schema = build_schema(fn)
    assert schema["function"]["description"] == "First line."


# ── combined annotations ──────────────────────────────────────────────────────


def test_annotated_optional_list():
    def fn(items: Annotated[list[str], "文件路径列表"] = None) -> str:  # type: ignore[assignment]
        """Test."""
        return ""

    schema = build_schema(fn)
    prop = schema["function"]["parameters"]["properties"]["items"]
    assert prop["type"] == "array"
    assert prop["items"] == {"type": "string"}
    assert prop["description"] == "文件路径列表"
    assert "items" not in schema["function"]["parameters"]["required"]
