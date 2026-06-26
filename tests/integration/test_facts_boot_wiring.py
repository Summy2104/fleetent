"""Integration tests: agent boot wires facts_store DB and the archive sweep."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from fleetent.memory import facts_store
from fleetent.runtime import agent_app as agent_app_module
from fleetent.runtime.agent_app import _init_agent_db_schema


def test_init_schema_injects_facts_db(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _init_agent_db_schema(data_dir, agent_id="agent-a", tenant_id="default")

    # facts_store must be usable after boot wiring (no RuntimeError).
    assert facts_store._facts_database() is not None
    clusters = facts_store.list_relation_clusters()
    assert {c.relation for c in clusters} >= {"is_role", "has_skill"}


def test_init_schema_source_calls_set_facts_db() -> None:
    src = inspect.getsource(agent_app_module._init_agent_db_schema)
    assert "facts_store.set_facts_db" in src


def test_start_infra_source_starts_archive_sweep() -> None:
    src = inspect.getsource(agent_app_module._start_infra)
    assert "start_archive_sweep" in src


def test_drain_source_stops_archive_sweep() -> None:
    src = inspect.getsource(agent_app_module._drain_and_close)
    assert "stop_archive_sweep" in src
