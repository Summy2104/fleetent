"""Integration tests: R2-叉2 — namespace second param removed (3b-3).

Verifies:
- vector_store.memory_namespace(user_id) is single-param, returns mem:{user_id}
- memory.search signature has no namespace parameter
- memory.extract_and_update signature has no namespace parameter
"""

from __future__ import annotations

import inspect


def test_memory_namespace_single_param() -> None:
    """memory_namespace must accept only user_id, return mem:{user_id}."""
    from fleetent.vector_store import memory_namespace

    result = memory_namespace("alice")
    assert result == "mem:alice"

    sig = inspect.signature(memory_namespace)
    params = list(sig.parameters)
    assert params == ["user_id"], f"memory_namespace must have only user_id param, got {params}"


def test_memory_namespace_rejects_second_positional() -> None:
    """Calling memory_namespace with two positional args must raise TypeError."""
    from fleetent.vector_store import memory_namespace
    import pytest

    with pytest.raises(TypeError):
        memory_namespace("alice", "analyst")  # type: ignore[call-arg]


def test_memory_search_has_no_namespace_param() -> None:
    """memory.search must not accept a namespace parameter."""
    from fleetent.memory import search

    sig = inspect.signature(search)
    assert "namespace" not in sig.parameters, (
        f"memory.search must not have namespace param, got {list(sig.parameters)}"
    )


def test_memory_extract_and_update_has_no_namespace_param() -> None:
    """memory.extract_and_update must not accept a namespace parameter."""
    from fleetent.memory import extract_and_update

    sig = inspect.signature(extract_and_update)
    assert "namespace" not in sig.parameters, (
        f"memory.extract_and_update must not have namespace param, got {list(sig.parameters)}"
    )
