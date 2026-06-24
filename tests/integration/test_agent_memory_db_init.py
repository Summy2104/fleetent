"""Integration: _init_agent_db_schema creates per-agent agent_memory.db, not shared_memory.db."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_init_agent_db_schema_creates_agent_memory_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After _init_agent_db_schema, per-agent agent_memory.db must exist under agent home data."""
    from fleetent.runtime import agent_app

    data_dir = tmp_path / "data"

    # Run the real schema init — uses real SQLite files under tmp_path
    with (
        patch("fleetent.reflection.set_state_db"),
        patch("fleetent.session.index.set_state_db"),
        patch("fleetent.observability.traces.set_state_db"),
        patch("fleetent.memory.store.set_state_db"),
        patch("fleetent.memory.store.set_vector_backend"),
        patch("fleetent.governance.approval_request_store.set_state_db"),
        patch("fleetent.governance.approval_store.set_state_db"),
        patch("fleetent.governance.tool_auto_approvals_store.set_state_db"),
        patch("fleetent.runtime.context.set_state_db"),
        patch("fleetent.runtime.sub_agent_lifecycle.set_state_db"),
        patch("fleetent.schedule_store.set_state_db"),
        patch("fleetent.im_gateway.outbound_queue_store.set_state_db"),
        patch("fleetent.artifact_exchange.set_state_db"),
        patch("fleetent.artifact_exchange.set_views_root"),
        patch("fleetent.knowledge_base.runtime.set_database"),
        patch("fleetent.knowledge_base.runtime.set_vector_backend"),
        patch("fleetent.memory.agent_memory.set_agent_memory_db"),
    ):
        agent_app._init_agent_db_schema(data_dir, agent_id="myagent", tenant_id="tenant1")

    agent_data_dir = tmp_path / "tenants" / "tenant1" / "agents" / "myagent" / "data"
    assert (agent_data_dir / "agent_memory.db").exists(), (
        "agent_memory.db must be created under per-agent data directory"
    )
    assert not (tmp_path / "tenants" / "tenant1" / "shared_memory.db").exists(), (
        "shared_memory.db must not exist — agent memory moved to per-agent scope"
    )


def test_init_agent_db_schema_no_shared_memory_db_at_tenant_level(
    tmp_path: Path,
) -> None:
    """The tenant directory must never contain shared_memory.db after the new init."""
    from fleetent.runtime import agent_app

    data_dir = tmp_path / "data"

    with (
        patch("fleetent.reflection.set_state_db"),
        patch("fleetent.session.index.set_state_db"),
        patch("fleetent.observability.traces.set_state_db"),
        patch("fleetent.memory.store.set_state_db"),
        patch("fleetent.memory.store.set_vector_backend"),
        patch("fleetent.governance.approval_request_store.set_state_db"),
        patch("fleetent.governance.approval_store.set_state_db"),
        patch("fleetent.governance.tool_auto_approvals_store.set_state_db"),
        patch("fleetent.runtime.context.set_state_db"),
        patch("fleetent.runtime.sub_agent_lifecycle.set_state_db"),
        patch("fleetent.schedule_store.set_state_db"),
        patch("fleetent.im_gateway.outbound_queue_store.set_state_db"),
        patch("fleetent.artifact_exchange.set_state_db"),
        patch("fleetent.artifact_exchange.set_views_root"),
        patch("fleetent.knowledge_base.runtime.set_database"),
        patch("fleetent.knowledge_base.runtime.set_vector_backend"),
        patch("fleetent.memory.agent_memory.set_agent_memory_db"),
    ):
        agent_app._init_agent_db_schema(data_dir, agent_id="bot", tenant_id="acme")

    tenant_dir = tmp_path / "tenants" / "acme"
    for path in tenant_dir.rglob("shared_memory*.db"):
        raise AssertionError(f"shared_memory*.db must not exist after new init, found: {path}")
