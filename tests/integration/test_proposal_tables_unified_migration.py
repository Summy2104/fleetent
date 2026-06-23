"""Unified reflection proposals live in one agent_state.db table across memory and skill."""

from fleetent.runtime.agent_state_migrations import MIGRATIONS
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter


def _boot_agent_state(tmp_path, agent_id="agent"):
    """Open a migrated per-agent agent_state.db and inject it into the agent-side stores."""
    from fleetent import reflection
    from fleetent.governance import approval_request_store
    from fleetent.memory import store as memory_store
    from fleetent.observability import traces

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path / "data"))
    db = router.agent_scope("default", agent_id).open_state_db(MIGRATIONS)
    reflection.set_state_db(db)
    approval_request_store.set_state_db(db)
    memory_store.set_state_db(db)
    traces.set_state_db(db)
    return db


def test_unified_reflection_proposals_list_pending_across_domains(tmp_path):
    from fleetent import reflection
    from fleetent.reflection import ReflectionFinding

    _boot_agent_state(tmp_path)

    memory_proposal = reflection.create_memory_maintenance_proposal(
        user_id="u1",
        action="mark_stale",
        target_memory_ids=["m1"],
        proposed_content=None,
        risk="low",
        reason="stale fact",
        evidence_ids=["trace-a"],
    )
    [proposal] = reflection.generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: triage incidents",
                evidence_ids=["trace-a", "trace-b"],
                metadata={"pattern": "triage incidents"},
            )
        ]
    )

    listed = reflection.list_reflection_proposals(status="pending")

    assert {(item.domain, item.id) for item in listed} == {
        ("memory", memory_proposal.id),
        ("skill", proposal.id),
    }

    memory_only = reflection.list_reflection_proposals(status="pending", domain="memory")
    skill_only = reflection.list_reflection_proposals(status="pending", domain="skill")

    assert [(item.domain, item.id) for item in memory_only] == [("memory", memory_proposal.id)]
    assert [(item.domain, item.id) for item in skill_only] == [("skill", proposal.id)]


async def test_unified_reflection_proposals_lifecycle_updates_single_table(tmp_path, monkeypatch):
    from fleetent import reflection
    from fleetent.reflection import ReflectionFinding

    _boot_agent_state(tmp_path)

    memory_calls: list[tuple[str, tuple[object, ...]]] = []
    skill_calls: list[str] = []

    async def mark_stale(user_id: str, memory_id: str) -> None:
        memory_calls.append(("mark_stale", (user_id, memory_id)))

    async def apply_skill(proposal) -> None:
        skill_calls.append(proposal.target_skill)

    monkeypatch.setattr(reflection.memory, "mark_user_memory_stale", mark_stale)
    monkeypatch.setattr(reflection, "apply_skill_proposal_to_boundary", apply_skill)

    memory_proposal = reflection.create_memory_maintenance_proposal(
        user_id="u1",
        action="mark_stale",
        target_memory_ids=["m1"],
        proposed_content=None,
        risk="low",
        reason="stale fact",
        evidence_ids=["trace-a"],
    )
    [skill_proposal] = reflection.generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: triage incidents",
                evidence_ids=["trace-a", "trace-b"],
                metadata={"pattern": "triage incidents"},
            )
        ]
    )

    approved_memory = reflection.approve_memory_maintenance_proposal(
        memory_proposal.id, actor_user_id="u1"
    )
    rejected_skill = reflection.reject_skill_proposal(
        skill_proposal.id,
        reviewer_user_id="reviewer-1",
        reason="not useful",
    )
    applied_memory = await reflection.apply_memory_maintenance_proposal(
        approved_memory.id,
        actor_user_id="u1",
    )

    listed = reflection.list_reflection_proposals(status=None)

    assert applied_memory.status == "applied"
    assert rejected_skill.status == "rejected"
    assert memory_calls == [("mark_stale", ("u1", "m1"))]
    assert skill_calls == []
    assert {(item.domain, item.status, item.id) for item in listed} == {
        ("memory", "applied", memory_proposal.id),
        ("skill", "rejected", skill_proposal.id),
    }


async def test_unified_apply_dispatch_is_domain_isolated(tmp_path, monkeypatch):
    from fleetent import reflection
    from fleetent.reflection import ReflectionFinding

    _boot_agent_state(tmp_path)

    memory_calls: list[str] = []
    skill_calls: list[str] = []

    async def mark_stale(user_id: str, memory_id: str) -> None:
        memory_calls.append(f"{user_id}:{memory_id}")

    async def apply_skill(proposal) -> None:
        skill_calls.append(proposal.target_skill)

    monkeypatch.setattr(reflection.memory, "mark_user_memory_stale", mark_stale)
    monkeypatch.setattr(reflection, "apply_skill_proposal_to_boundary", apply_skill)

    memory_proposal = reflection.create_memory_maintenance_proposal(
        user_id="u1",
        action="mark_stale",
        target_memory_ids=["m1"],
        proposed_content=None,
        risk="low",
        reason="stale fact",
        evidence_ids=["trace-a"],
    )
    [skill_proposal] = reflection.generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: ship release",
                evidence_ids=["trace-a", "trace-b"],
                metadata={"pattern": "ship release"},
            )
        ]
    )

    reflection.approve_memory_maintenance_proposal(memory_proposal.id, actor_user_id="u1")
    reflection.approve_skill_proposal(skill_proposal.id, reviewer_user_id="reviewer-1")
    await reflection.apply_memory_maintenance_proposal(memory_proposal.id, actor_user_id="u1")
    await reflection.apply_skill_proposal(skill_proposal.id, actor_user_id="reviewer-1")

    assert memory_calls == ["u1:m1"]
    assert skill_calls == ["ship-release"]


async def test_pending_memory_proposal_notifies_agent_owned_approvers(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from fleetent import agent_config, reflection
    from fleetent.governance.permission_gate import PermissionGate

    _boot_agent_state(tmp_path)

    notified: list[tuple[str, str, str, dict[str, object]]] = []
    connector = object()

    async def notify(
        self, *, approval_id, tool_name, risk_level, approval_routing, outbound_connectors
    ):
        notified.append((approval_id, tool_name, risk_level, outbound_connectors))
        return ["slack:U_OWNER"]

    monkeypatch.setattr(
        agent_config,
        "active_agent",
        lambda: SimpleNamespace(
            approval=agent_config.ApprovalRouting(
                by_tool={
                    "reflection_memory_proposal": agent_config.ApprovalEntry(
                        approvers=["slack:U_OWNER"],
                        policy="any",
                    )
                }
            )
        ),
    )
    monkeypatch.setattr(PermissionGate, "_notify_approvers", notify)
    monkeypatch.setattr(
        reflection,
        "_approval_outbound_connectors_provider",
        lambda: {"slack": connector},
    )

    proposal = reflection.create_memory_maintenance_proposal(
        user_id="u1",
        action="mark_stale",
        target_memory_ids=["m1"],
        proposed_content=None,
        risk="low",
        reason="stale fact",
        evidence_ids=["trace-a"],
    )

    await asyncio.sleep(0)

    assert notified == [(proposal.id, "reflection_memory_proposal", "low", {"slack": connector})]


async def test_pending_skill_proposal_without_approver_stays_pending_and_sends_nothing(
    tmp_path, monkeypatch
):
    import asyncio
    from types import SimpleNamespace

    from fleetent import agent_config, reflection
    from fleetent.governance.permission_gate import PermissionGate
    from fleetent.reflection import ReflectionFinding

    _boot_agent_state(tmp_path)

    notified: list[str] = []

    async def notify(
        self, *, approval_id, tool_name, risk_level, approval_routing, outbound_connectors
    ):
        notified.append(approval_id)
        return []

    monkeypatch.setattr(
        agent_config,
        "active_agent",
        lambda: SimpleNamespace(
            approval=agent_config.ApprovalRouting(
                by_tool={
                    "reflection_skill_proposal": agent_config.ApprovalEntry(
                        approvers=[],
                        policy="any",
                    )
                }
            )
        ),
    )
    monkeypatch.setattr(PermissionGate, "_notify_approvers", notify)

    [proposal] = reflection.generate_skill_proposals(
        findings=[
            ReflectionFinding(
                type="skill_opportunity",
                summary="Repeated task pattern may become a skill: sync notes",
                evidence_ids=["trace-a", "trace-b"],
                metadata={"pattern": "sync notes"},
            )
        ]
    )

    await asyncio.sleep(0)

    assert reflection.get_skill_proposal(proposal.id).status == "pending"
    assert notified == []


async def test_reflection_proposal_creates_unified_approval_request_and_router_applies(
    tmp_path, monkeypatch
):
    import asyncio
    from types import SimpleNamespace

    from fleetent import agent_config, reflection
    from fleetent.governance import approval_request_store, approval_router
    from fleetent.governance.permission_gate import PermissionGate
    from fleetent.memory import agent_memory as agent_memory_module

    _boot_agent_state(tmp_path)

    notified: list[str] = []
    applied: list[str] = []

    async def notify(
        self, *, approval_id, tool_name, risk_level, approval_routing, outbound_connectors
    ):
        notified.append(approval_id)
        return ["slack:u1"]

    async def apply_agent_memory_proposal(proposal_id: str, actor_id: str) -> None:
        applied.append(f"{proposal_id}:{actor_id}")

    monkeypatch.setattr(
        agent_config,
        "active_agent",
        lambda: SimpleNamespace(
            approval=agent_config.ApprovalRouting(
                by_tool={
                    "reflection_agent_memory_proposal": agent_config.ApprovalEntry(
                        approvers=["slack:u1"],
                        policy="any",
                    )
                }
            )
        ),
    )
    monkeypatch.setattr(PermissionGate, "_notify_approvers", notify)
    monkeypatch.setattr(agent_memory_module, "apply_agent_memory_proposal", apply_agent_memory_proposal)

    proposal = reflection.create_memory_maintenance_proposal(
        user_id="u1",
        action="suggest_agent_memory_or_kb",
        target_memory_ids=[],
        proposed_content="A stable org fact",
        risk="low",
        reason="agent memory fact",
        evidence_ids=["trace-a"],
        metadata_patch={"target": "agent_memory"},
    )

    await asyncio.sleep(0)

    request = approval_request_store.get_request(proposal.id)
    assert request is not None
    assert request["subject_type"] == "memory_proposal"
    assert request["status"] == "pending"
    assert request["routing_key"] == "reflection_agent_memory_proposal"
    assert notified == [proposal.id]

    ok = await approval_router.resolve_approval_request(
        approval_id=proposal.id,
        decision="approved",
        approver_user_id="u1",
    )

    assert ok is True
    updated = approval_request_store.get_request(proposal.id)
    assert updated is not None
    assert updated["status"] == "approved"
    assert updated["approver_user_id"] == "u1"
    assert applied == [f"{proposal.id}:u1"]
