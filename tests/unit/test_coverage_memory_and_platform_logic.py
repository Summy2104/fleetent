from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from fleetent.memory import extraction, maintenance, shared, trends
from fleetent.memory.models import (
    MemoryCompactionCandidate,
    MemoryItem,
    MemoryMaintenancePolicy,
    SharedMemoryItem,
)
from fleetent.platform.model_provider_management import provider_connectivity
from fleetent.platform.resource_monitoring import alerting


def _memory_item(
    id: str,
    type: str = "identity",
    content: str = "User is an engineer",
    updated_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> MemoryItem:
    now = updated_at or datetime(2026, 1, 1, tzinfo=UTC)
    return MemoryItem(
        id=id,
        user_id="u1",
        type=type,  # type: ignore[arg-type]
        content=content,
        created_at=now,
        updated_at=now,
        expires_at=expires_at,
        namespace="work",
    )


def _shared_item(
    id: str = "sm1",
    status: str = "active",
    type: str = "context",
    content: str = "Deploys happen on Fridays",
) -> SharedMemoryItem:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return SharedMemoryItem(
        id=id,
        scope_type="team",
        scope_id="eng",
        type=type,  # type: ignore[arg-type]
        content=content,
        status=status,  # type: ignore[arg-type]
        source="manual",
        source_ref=None,
        created_by="admin",
        created_at=now,
        updated_at=now,
    )


def test_memory_extraction_parses_provider_wrapped_arrays_and_normalizes_content():
    assert extraction.strip_markdown_fence("```json\n[]\n```") == "[]"
    assert extraction.parse_action_array('prefix [{"action":"ignore"}] suffix') == [
        {"action": "ignore"}
    ]
    assert extraction.parse_action_array('```json\n[{"action":"create"}]\n```') == [
        {"action": "create"}
    ]
    assert extraction.parse_action_array("not json") is None

    assert extraction.normalize_action_content("identity", " i am platform lead ") == (
        "User is platform lead"
    )
    assert extraction.normalize_action_content("identity", "my name is Randy") == (
        "User's name is Randy"
    )
    assert extraction.normalize_action_content("identity", "architect") == "User is a architect"
    assert extraction.normalize_action_content("preferences", "prefers concise updates") == (
        "User prefers concise updates"
    )
    assert extraction.normalize_action_content("preferences", "my preference is dark mode") == (
        "User prefers dark mode"
    )
    assert extraction.normalize_action_content("context", "working on coverage") == (
        "User is working on coverage"
    )
    assert extraction.normalize_action_content("context", "currently migrating tests") == (
        "User is currently migrating tests"
    )
    assert extraction.targets_non_user_memory({"destination": "knowledge_base"})
    assert not extraction.targets_non_user_memory({"destination": "user_memory"})


def test_memory_extraction_message_renders_snapshot_and_skips_system_roles():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    snapshot = {
        "identity": [_memory_item("m1", updated_at=now)],
        "preferences": [],
        "context": [],
    }

    message = extraction.extraction_user_message(
        [
            {"role": "system", "content": "hidden"},
            {"role": "user", "content": "remember I like tea"},
            {"role": "tool", "content": "hidden"},
            {"role": "assistant", "content": "ok"},
        ],
        snapshot,  # type: ignore[arg-type]
    )

    assert "Existing memory snapshot:" in message
    assert '"id": "m1"' in message
    assert "user: remember I like tea" in message
    assert "assistant: ok" in message
    assert "hidden" not in message


async def test_extract_and_update_applies_valid_actions_and_skips_invalid_targets(monkeypatch):
    existing = _memory_item("existing", type="preferences", content="User prefers tea")
    deleted = _memory_item("deleted", type="context", content="User is working on old task")
    inserted: list[MemoryItem] = []
    updated: list[MemoryItem] = []
    deleted_ids: list[str] = []
    vector_upserts: list[tuple[str, str, str]] = []
    vector_deletes: list[tuple[str, str]] = []

    actions = [
        {"action": "create", "type": "identity", "content": "i am an operator"},
        {
            "action": "update",
            "target_id": "existing",
            "type": "preferences",
            "content": "i prefer terse summaries",
        },
        {"action": "delete", "target_id": "deleted"},
        {"action": "create", "type": "context", "content": "working on ignored", "target": "kb"},
        {"action": "update", "target_id": "missing", "type": "identity", "content": "ignored"},
        {"action": "create", "type": "unknown", "content": "ignored"},
        {"action": "ignore", "type": "identity", "content": "ignored"},
        "not a dict",
    ]

    class FakeCompletions:
        async def create(self, **_: Any) -> Any:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content=str(actions).replace("'", '"')))
                ]
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    monkeypatch.setattr(extraction, "AsyncOpenAI", lambda **_: fake_client)
    from fleetent.agent_config import AgentFile
    from fleetent.model import ModelPolicySnapshot

    policy = ModelPolicySnapshot.from_agent(
        AgentFile.model_validate(
            {
                "name": "memory-agent",
                "version": 1,
                "models": {
                    "targets": [
                        {
                            "id": "memory",
                            "provider": "local",
                            "protocol": "openai_chat",
                            "base_url": "http://memory.local/v1/",
                            "model": "m",
                            "max_tokens": 200,
                        }
                    ],
                    "routes": {"memory_extraction": [{"target": "memory"}]},
                },
            }
        )
    )
    monkeypatch.setattr(
        extraction.store,
        "memory_snapshot",
        lambda _user_id, _namespace: {
            "identity": [],
            "preferences": [existing],
            "context": [deleted],
        },
    )
    monkeypatch.setattr(extraction.store, "insert_memory", inserted.append)
    monkeypatch.setattr(extraction.store, "update_memory", updated.append)
    monkeypatch.setattr(
        extraction.store, "delete_memory", lambda _user_id, id: deleted_ids.append(id)
    )
    monkeypatch.setattr(
        extraction.vector_store, "memory_namespace", lambda user_id, ns: f"{user_id}:{ns}"
    )

    async def fake_upsert(id: str, content: str, namespace: str) -> None:
        vector_upserts.append((id, content, namespace))

    async def fake_delete(id: str, namespace: str) -> None:
        vector_deletes.append((id, namespace))

    monkeypatch.setattr(extraction.vector_store, "upsert", fake_upsert)
    monkeypatch.setattr(extraction.vector_store, "delete", fake_delete)

    await extraction.extract_and_update(
        "u1", [{"role": "user", "content": "facts"}], "work", model_policy=policy
    )

    assert [item.content for item in inserted] == ["User is an operator"]
    assert [(item.id, item.content, item.expires_at) for item in updated] == [
        ("existing", "User prefers terse summaries", None)
    ]
    assert deleted_ids == ["deleted"]
    assert [(content, namespace) for _id, content, namespace in vector_upserts] == [
        ("User is an operator", "u1:work"),
        ("User prefers terse summaries", "u1:work"),
    ]
    assert vector_deletes == [("deleted", "u1:work")]


def test_memory_trends_buckets_counts_and_filters_with_fake_store(monkeypatch):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    query = trends.MemoryQualityTrendQuery(
        user_id="u1",
        scope_type="team",
        scope_id="eng",
        start_ts=start,
        end_ts=start + timedelta(days=2),
        bucket="day",
    )

    memory_rows = [
        {
            "id": "m1",
            "user_id": "u1",
            "type": "context",
            "content": "Same",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T01:00:00+00:00",
            "expires_at": "2026-01-02T01:00:00+00:00",
        },
        {
            "id": "m2",
            "user_id": "u1",
            "type": "context",
            "content": " same ",
            "created_at": "2026-01-02T00:00:00+00:00",
            "updated_at": "2026-01-02T02:00:00+00:00",
            "expires_at": None,
        },
        {
            "id": "outside",
            "user_id": "u1",
            "type": "identity",
            "content": "outside",
            "created_at": "2026-01-03T00:00:00+00:00",
            "updated_at": "2026-01-03T00:00:00+00:00",
            "expires_at": None,
        },
    ]
    shared_rows = [
        {
            "id": "s1",
            "scope_type": "team",
            "scope_id": "eng",
            "type": "procedure",
            "status": "active",
            "updated_at": "2026-01-01T04:00:00+00:00",
        }
    ]

    class FakeCursor:
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self.rows = rows

        def fetchall(self) -> list[dict[str, Any]]:
            return self.rows

    class FakeDb:
        def execute(self, sql: str, params: dict[str, object]) -> FakeCursor:
            assert params["start_ts"] == "2026-01-01T00:00:00+00:00"
            if "FROM memory_items" in sql:
                assert params["user_id"] == "u1"
                return FakeCursor(memory_rows)
            assert "FROM shared_memory_items" in sql
            assert params["scope_type"] == "team"
            assert params["scope_id"] == "eng"
            return FakeCursor(shared_rows)

    proposals = [
        SimpleNamespace(
            updated_at=start + timedelta(hours=3),
            status="open",
            action="delete",
            risk="low",
        ),
        SimpleNamespace(
            updated_at=start + timedelta(days=3),
            status="ignored",
            action="merge",
            risk="high",
        ),
    ]
    monkeypatch.setattr(trends.store, "database", lambda: FakeDb())
    monkeypatch.setattr(trends, "_list_memory_maintenance_proposals", lambda user_id: proposals)

    summary = trends.get_memory_quality_trend_summary(query)

    assert len(summary.buckets) == 2
    assert summary.buckets[0].user_memory_counts == {"context": 1}
    assert summary.buckets[0].shared_memory_counts == {"procedure": 1}
    assert summary.buckets[0].proposal_status_counts == {"open": 1}
    assert summary.buckets[0].proposal_action_counts == {"delete": 1}
    assert summary.buckets[0].proposal_risk_counts == {"low": 1}
    assert summary.buckets[1].expired_context_count == 1
    assert summary.buckets[1].duplicate_candidate_count == 1


def test_memory_trends_rejects_invalid_ranges_and_bucket_names():
    now = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="end_ts"):
        trends._build_empty_buckets(  # noqa: SLF001
            trends.MemoryQualityTrendQuery(None, None, None, now, now, "day")
        )
    with pytest.raises(ValueError, match="bucket"):
        trends._build_empty_buckets(  # noqa: SLF001
            trends.MemoryQualityTrendQuery(None, None, None, now, now + timedelta(days=1), "month")  # type: ignore[arg-type]
        )
    assert (
        trends._memory_maintenance_proposals(  # noqa: SLF001
            trends.MemoryQualityTrendQuery(None, None, None, now, now + timedelta(days=1), "day")
        )
        == []
    )


async def test_memory_maintenance_dry_run_and_delete_paths(monkeypatch):
    candidate = MemoryCompactionCandidate(
        type="context",
        canonical_id="keep",
        duplicate_ids=["dup", "expired"],
        reason="same normalized content",
    )
    deleted: list[tuple[str, str]] = []
    vector_deleted: list[tuple[str, str]] = []

    monkeypatch.setattr(maintenance.store, "expired_context_ids", lambda user_id: ["expired"])
    monkeypatch.setattr(
        maintenance.store, "over_limit_ids", lambda user_id, policy: ["over", "dup"]
    )
    monkeypatch.setattr(
        maintenance.store, "duplicate_compaction_candidates", lambda user_id: [candidate]
    )
    monkeypatch.setattr(
        maintenance.store, "delete_memory", lambda user_id, id: deleted.append((user_id, id))
    )
    monkeypatch.setattr(
        maintenance.vector_store, "memory_namespace", lambda user_id: f"memory:{user_id}"
    )

    async def fake_vector_delete(id: str, namespace: str) -> None:
        vector_deleted.append((id, namespace))

    monkeypatch.setattr(maintenance.vector_store, "delete", fake_vector_delete)

    dry = await maintenance.run_memory_maintenance("u1", dry_run=True)
    assert dry.deleted_ids == ["expired", "over", "dup"]
    assert dry.expired_count == 1
    assert dry.over_limit_count == 2
    assert dry.compacted_count == 2
    assert deleted == []

    wet = await maintenance.run_memory_maintenance(
        "u1", policy=MemoryMaintenancePolicy(compact_duplicates=False), dry_run=False
    )
    assert wet.compaction_candidates == []
    assert deleted == [("u1", "expired"), ("u1", "over"), ("u1", "dup")]
    assert vector_deleted == [
        ("expired", "memory:u1"),
        ("over", "memory:u1"),
        ("dup", "memory:u1"),
    ]


def test_memory_maintenance_validation_and_dedupe():
    with pytest.raises(ValueError, match="user_id"):
        maintenance.validate_maintenance_request(" ", MemoryMaintenancePolicy())
    with pytest.raises(ValueError, match="max_identity"):
        maintenance.validate_maintenance_request("u1", MemoryMaintenancePolicy(max_identity=-1))
    assert maintenance.dedupe_ids(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


async def test_shared_memory_validators_mapping_and_vector_sync(monkeypatch):
    active = _shared_item(status="active")
    archived = _shared_item(id="sm2", status="archived")
    upserts: list[tuple[str, str, str]] = []
    deletes: list[tuple[str, str]] = []

    monkeypatch.setattr(shared.vector_store, "shared_namespace", lambda scope, id: f"{scope}:{id}")

    async def fake_upsert(id: str, content: str, namespace: str) -> None:
        upserts.append((id, content, namespace))

    async def fake_delete(id: str, namespace: str) -> None:
        deletes.append((id, namespace))

    monkeypatch.setattr(shared.vector_store, "upsert", fake_upsert)
    monkeypatch.setattr(shared.vector_store, "delete", fake_delete)

    assert shared._validate_scope_type("team") == "team"  # noqa: SLF001
    assert shared._validate_type("procedure") == "procedure"  # noqa: SLF001
    assert shared._validate_status("stale") == "stale"  # noqa: SLF001
    assert shared._validate_source("reflection_proposal") == "reflection_proposal"  # noqa: SLF001
    assert shared._validate_non_empty(" value ", "field") == "value"  # noqa: SLF001
    assert shared._require_proposed_content(" proposed ") == "proposed"  # noqa: SLF001
    with pytest.raises(ValueError, match="scope_type"):
        shared._validate_scope_type("workspace")  # noqa: SLF001
    with pytest.raises(ValueError, match="type"):
        shared._validate_type("identity")  # noqa: SLF001
    with pytest.raises(ValueError, match="status"):
        shared._validate_status("deleted")  # noqa: SLF001
    with pytest.raises(ValueError, match="source"):
        shared._validate_source("sync")  # noqa: SLF001
    with pytest.raises(ValueError, match="content"):
        shared._validate_content(" ")  # noqa: SLF001
    with pytest.raises(ValueError, match="proposed_content"):
        shared._require_proposed_content(None)  # noqa: SLF001

    row = shared._params(active)  # noqa: SLF001
    assert row["created_at"] == "2026-01-01T00:00:00+00:00"
    assert shared._row_to_item(row).content == active.content  # noqa: SLF001

    await shared._sync_vector(active)  # noqa: SLF001
    await shared._sync_vector(archived)  # noqa: SLF001
    assert upserts == [("sm1", "Deploys happen on Fridays", "team:eng")]
    assert deletes == [("sm2", "team:eng")]


async def test_shared_memory_search_and_listing_use_fake_database(monkeypatch):
    rows = [
        shared._params(_shared_item("first", status="active")),  # noqa: SLF001
        shared._params(_shared_item("second", status="stale")),  # noqa: SLF001
        shared._params(_shared_item("archived", status="archived")),  # noqa: SLF001
    ]
    executed: list[tuple[str, dict[str, object]]] = []

    class FakeCursor:
        def __init__(self, result: list[dict[str, object]] | dict[str, object] | None) -> None:
            self.result = result

        def fetchall(self) -> list[dict[str, object]]:
            assert isinstance(self.result, list)
            return self.result

        def fetchone(self) -> dict[str, object] | None:
            assert self.result is None or isinstance(self.result, dict)
            return self.result

    class FakeDb:
        def execute(self, sql: str, params: dict[str, object]) -> FakeCursor:
            executed.append((sql, params))
            if "WHERE id = :id" in sql:
                return FakeCursor(rows[0] if params["id"] == "first" else None)
            if "id IN" in sql:
                return FakeCursor(rows)
            return FakeCursor(rows)

    monkeypatch.setattr(shared.store, "database", lambda: FakeDb())

    async def fake_search(_query: str, _namespace: str, _limit: int) -> list[Any]:
        return [
            SimpleNamespace(id="archived"),
            SimpleNamespace(id="second"),
            SimpleNamespace(id="missing"),
            SimpleNamespace(id="first"),
        ]

    monkeypatch.setattr(shared.vector_store, "search", fake_search)
    monkeypatch.setattr(shared.vector_store, "shared_namespace", lambda scope, id: f"{scope}:{id}")

    assert shared.get_shared_memory("first").id == "first"
    with pytest.raises(ValueError, match="does not exist"):
        shared.get_shared_memory("missing")
    assert [item.id for item in shared.list_shared_memory("team", "eng")] == [
        "first",
        "second",
        "archived",
    ]
    indexable = list(shared.iter_indexable_shared_memories("team", "eng"))
    assert [(item.id, item.namespace) for item in indexable] == [
        ("first", "team:eng"),
        ("second", "team:eng"),
        ("archived", "team:eng"),
    ]
    search_results = await shared.search_shared_memory("team", "eng", "deploy", limit=4)
    assert [item.id for item in search_results] == ["second", "first"]


def test_shared_memory_new_item_insert_update_and_audit_paths(monkeypatch):
    inserted: list[dict[str, object]] = []

    class FakeDb:
        def execute(self, _sql: str, params: dict[str, object]) -> None:
            inserted.append(params)

    monkeypatch.setattr(shared.store, "database", lambda: FakeDb())
    item = shared._new_item(  # noqa: SLF001
        scope_type="team",
        scope_id="eng",
        type="context",
        content=" runbooks live in docs ",
        created_by=" admin ",
        source="manual",
        source_ref=None,
    )
    assert item.content == "runbooks live in docs"
    assert item.created_by == "admin"

    shared._insert(item)  # noqa: SLF001
    shared._update(item)  # noqa: SLF001
    assert [params["id"] for params in inserted] == [item.id, item.id]

    events: list[Any] = []
    monkeypatch.setattr(
        "fleetent.observability.record_trace_event",
        lambda event: events.append(event),
    )
    from fleetent.platform.admin_cli import shared_memory

    shared_memory.record_shared_memory_admin_audit("create", item.id, "admin")
    assert events[0].payload == {"action": "create", "item_id": item.id, "actor": "admin"}


def test_shared_memory_audit_not_implemented_in_memory_core(monkeypatch):
    """Shared-memory admin audit should be implemented in platform shell, not core."""

    assert not hasattr(shared, "record_shared_memory_admin_audit")

    events: list[Any] = []
    monkeypatch.setattr(
        "fleetent.platform.admin_cli.shared_memory.observability.record_trace_event",
        lambda event: events.append(event),
    )
    from fleetent.platform.admin_cli import shared_memory

    shared_memory.record_shared_memory_admin_audit("shared_memory.create", "item-1", "admin")
    assert events[0].payload == {
        "action": "shared_memory.create",
        "item_id": "item-1",
        "actor": "admin",
    }


def test_alerting_evaluates_sustained_breaches_and_suppression():
    now = datetime(2026, 1, 1, 12, 0)
    rule = {"enabled": 1, "for_seconds": 60, "comparator": ">=", "threshold": 90}
    samples = [
        {"ts": "2026-01-01T11:58:30", "value": 91},
        {"ts": "2026-01-01T11:59:30", "value": 92},
        {"ts": "2026-01-01T12:00:00", "value": 95},
    ]
    assert alerting.breach(91, ">=", 90)
    assert not alerting.breach(89, ">=", 90)
    assert alerting.evaluate(rule, samples, now)
    assert not alerting.evaluate({**rule, "enabled": 0}, samples, now)
    assert not alerting.evaluate(rule, [{"ts": "2026-01-01T12:00:00", "value": 95}], now)
    assert not alerting.evaluate(
        rule,
        [{"ts": "2026-01-01T11:58:30", "value": 80}, {"ts": "2026-01-01T12:00:00", "value": 95}],
        now,
    )
    assert not alerting.evaluate(rule, [], now)
    assert alerting.in_maintenance(
        [{"target": None, "start_ts": "2026-01-01T11:00:00", "end_ts": "2026-01-01T13:00:00"}],
        "host:h1",
        now,
    )
    assert not alerting.in_maintenance(
        [{"target": "host:h2", "start_ts": "2026-01-01T11:00:00", "end_ts": "2026-01-01T13:00:00"}],
        "host:h1",
        now,
    )
    assert alerting.is_suppressed("host:h1/container:c1", {"host:h1"})
    assert not alerting.is_suppressed("host:h1", {"host:h1"})
    assert alerting.should_escalate(
        {"severity": "critical", "status": "notified", "fired_at": "2026-01-01T11:00:00"},
        now,
        1800,
    )
    assert not alerting.should_escalate(
        {"severity": "warning", "status": "notified", "fired_at": "2026-01-01T11:00:00"},
        now,
        1800,
    )


async def test_provider_connectivity_handles_success_and_errors(monkeypatch):
    created_clients: list[dict[str, Any]] = []

    class FakeCompletions:
        def __init__(self, outcome: Exception | None = None) -> None:
            self.outcome = outcome

        async def create(self, **kwargs: Any) -> None:
            assert kwargs["messages"] == [{"role": "user", "content": "Hi"}]
            assert kwargs["max_tokens"] == 1
            if self.outcome is not None:
                raise self.outcome

    class FakeOpenAI:
        outcome: Exception | None = None

        def __init__(self, **kwargs: Any) -> None:
            created_clients.append(kwargs)
            self.chat = SimpleNamespace(completions=FakeCompletions(self.outcome))

    monkeypatch.setattr(provider_connectivity, "AsyncOpenAI", FakeOpenAI)

    result = await provider_connectivity.test_provider_connectivity(
        {"base_url": "https://llm.local/v1", "model": "gpt-test", "api_key": "secret"}
    )
    assert result["reachable"] is True
    assert isinstance(result["latency_ms"], int)
    assert result["model"] == "gpt-test"
    assert result["error"] is None
    assert created_clients[0]["base_url"] == "https://llm.local/v1"
    assert created_clients[0]["api_key"] == "secret"

    assert await provider_connectivity.test_provider_connectivity({"model": "gpt-test"}) == {
        "reachable": False,
        "latency_ms": None,
        "model": "gpt-test",
        "error": "Missing base_url or model configuration",
    }

    for error, expected in (
        (httpx.ConnectError("down"), "Connection failed: down"),
        (httpx.TimeoutException("slow"), "Request timed out (10s)"),
        (RuntimeError("boom"), "Unexpected error: RuntimeError: boom"),
    ):
        FakeOpenAI.outcome = error
        result = await provider_connectivity.test_provider_connectivity(
            {"base_url": "https://llm.local/v1", "model": "gpt-test"}
        )
        assert result["reachable"] is False
        assert result["model"] == "gpt-test"
        assert result["error"] == expected


def test_provider_connectivity_sync_uses_asyncio_run(monkeypatch):
    calls: list[dict[str, Any]] = []

    async def fake_connectivity(provider: dict[str, Any]) -> dict[str, Any]:
        calls.append(provider)
        return {"reachable": True}

    monkeypatch.setattr(provider_connectivity, "test_provider_connectivity", fake_connectivity)

    assert provider_connectivity.test_provider_connectivity_sync({"model": "m"}) == {
        "reachable": True
    }
    assert calls == [{"model": "m"}]
