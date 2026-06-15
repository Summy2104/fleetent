"""Unit tests: run_as must never appear in LLM-visible tool schemas (P4 task 2.2)."""

from __future__ import annotations

import copy


def test_run_as_not_in_connector_tool_schema():
    """run_as is a grant-table property; it must never appear in the LLM-visible tool schema."""
    from fleetent.tools import registry

    saved_registry = copy.copy(registry._registry)
    saved_connectors = copy.copy(registry._connectors)
    saved_availability = copy.copy(registry._availability)

    try:
        def _dummy(msg: str) -> str:
            """Dummy connector tool."""
            return msg

        schema = {
            "name": "_test_run_as_sentry",
            "description": "Dummy connector tool.",
            "input_schema": {
                "type": "object",
                "properties": {"msg": {"type": "string"}},
                "required": ["msg"],
            },
        }
        registry._registry["_test_run_as_sentry"] = (_dummy, schema)
        registry._connectors["_test_run_as_sentry"] = ("test_svc", [])

        schemas = registry.get_schemas()
        target = next((s for s in schemas if s.get("name") == "_test_run_as_sentry"), None)
        assert target is not None, "dummy tool schema not found"

        props = target.get("input_schema", {}).get("properties", {})
        assert "run_as" not in props, "run_as must not appear in LLM-visible tool schema properties"
    finally:
        registry._registry.clear()
        registry._registry.update(saved_registry)
        registry._connectors.clear()
        registry._connectors.update(saved_connectors)
        registry._availability.clear()
        registry._availability.update(saved_availability)
