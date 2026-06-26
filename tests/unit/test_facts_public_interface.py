"""Unit tests: deprecated search()/extract_and_update + new facts API exposure."""

from __future__ import annotations

import warnings

import pytest


def test_legacy_search_raises_deprecation_warning() -> None:
    from fleetent.memory import search

    with pytest.warns(DeprecationWarning):
        result = search("u1", "query")  # legacy signature, no DB needed
    assert result == []


async def test_legacy_extract_and_update_raises_deprecation_warning() -> None:
    from fleetent.memory import extract_and_update

    with pytest.warns(DeprecationWarning):
        await extract_and_update("u1", [])


def test_new_facts_api_exposed() -> None:
    import fleetent.memory as memory

    assert hasattr(memory, "search_facts")
    assert hasattr(memory, "run_pipeline")
    assert hasattr(memory, "pin_fact")
    assert hasattr(memory, "retract_fact")
    assert hasattr(memory, "set_facts_db")
