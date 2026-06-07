"""Tests for @tool availability declaration (tool-availability spec)."""

import pytest

from fleetent.tools import registry as tr


@pytest.fixture(autouse=True)
def clean_registry():
    before = dict(tr._registry)
    before_risk = dict(tr._risk_levels)
    before_avail = dict(tr._availability)
    yield
    tr._registry.clear()
    tr._registry.update(before)
    tr._risk_levels.clear()
    tr._risk_levels.update(before_risk)
    tr._availability.clear()
    tr._availability.update(before_avail)


def test_tool_without_availability_always_in_schemas():
    @tr.tool
    def always_tool(x: str) -> str:
        """Always available."""
        return x

    schemas = tr.get_schemas()
    names = [s["function"]["name"] for s in schemas]
    assert "always_tool" in names


def test_tool_with_availability_true_in_schemas():
    @tr.tool(availability=lambda: True)
    def avail_true(x: str) -> str:
        """Available when lambda is True."""
        return x

    names = [s["function"]["name"] for s in tr.get_schemas()]
    assert "avail_true" in names


def test_tool_with_availability_false_excluded_from_schemas():
    @tr.tool(availability=lambda: False)
    def avail_false(x: str) -> str:
        """Never available."""
        return x

    names = [s["function"]["name"] for s in tr.get_schemas()]
    assert "avail_false" not in names


def test_availability_evaluated_each_call(monkeypatch):
    state = {"available": False}

    @tr.tool(availability=lambda: state["available"])
    def dynamic_tool(x: str) -> str:
        """Dynamically available."""
        return x

    assert "dynamic_tool" not in [s["function"]["name"] for s in tr.get_schemas()]
    state["available"] = True
    assert "dynamic_tool" in [s["function"]["name"] for s in tr.get_schemas()]


def test_availability_exception_treated_as_unavailable(caplog):
    import logging

    def bad_check() -> bool:
        raise RuntimeError("check failed")

    @tr.tool(availability=bad_check)
    def fragile_tool(x: str) -> str:
        """Fragile check."""
        return x

    with caplog.at_level(logging.WARNING):
        names = [s["function"]["name"] for s in tr.get_schemas()]

    assert "fragile_tool" not in names
    assert any("fragile_tool" in r.message or "availability" in r.message for r in caplog.records)


def test_unavailable_tool_remains_in_registry():
    @tr.tool(availability=lambda: False)
    def hidden_tool(x: str) -> str:
        """Hidden but still registered."""
        return x

    assert "hidden_tool" in tr._registry


def test_dispatch_still_works_for_unavailable_tool():
    @tr.tool(availability=lambda: False)
    def hidden_dispatch(x: str) -> str:
        """Hidden but dispatchable."""
        return f"ok:{x}"

    result = tr.dispatch("hidden_dispatch", '{"x": "v"}')
    assert result == "ok:v"


def test_availability_none_same_as_no_declaration():
    @tr.tool(availability=None)
    def avail_none(x: str) -> str:
        """availability=None means always available."""
        return x

    names = [s["function"]["name"] for s in tr.get_schemas()]
    assert "avail_none" in names
