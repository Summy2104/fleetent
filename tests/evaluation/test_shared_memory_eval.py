import json
from pathlib import Path

from fleetent.db import create_database
from fleetent.intelligence.vector_store import SearchResult

FIXTURE = Path("tests/evaluation/fixtures/shared_memory/basic.json")


async def test_shared_memory_evaluation_covers_scope_archive_and_proposal_apply(
    monkeypatch, tmp_path
):
    from fleetent.intelligence import memory, reflection
    from fleetent.intelligence.memory import shared, store
    from tests.integration.test_migrations import apply_migrations

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    db_path = tmp_path / "shared-memory-eval.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(store, "database", lambda: database)
    monkeypatch.setattr(reflection, "_database", lambda: database)
    monkeypatch.setattr(reflection.observability, "record_trace_event", lambda event: None)

    indexed: dict[str, tuple[str, str]] = {}

    async def upsert(id: str, text: str, namespace: str) -> None:
        indexed[id] = (text, namespace)

    async def delete(id: str, namespace: str) -> None:
        indexed.pop(id, None)

    async def search(query: str, namespace: str, limit: int = 10) -> list[SearchResult]:
        matches = [
            SearchResult(id=item_id, score=1.0)
            for item_id, (text, item_namespace) in indexed.items()
            if item_namespace == namespace and query.lower().split()[0] in text.lower()
        ]
        return matches[:limit]

    monkeypatch.setattr(shared.vector_store, "upsert", upsert)
    monkeypatch.setattr(shared.vector_store, "delete", delete)
    monkeypatch.setattr(shared.vector_store, "search", search)

    for item in fixture["items"]:
        created = await memory.create_shared_memory(
            scope_type=fixture["scope_type"],
            scope_id=fixture["scope_id"],
            type=item["type"],
            content=item["content"],
            created_by="eval",
        )
        results = await memory.search_shared_memory(
            fixture["scope_type"],
            fixture["scope_id"],
            item["expected_query"],
        )
        assert created.id in {result.id for result in results}

    archived = await memory.create_shared_memory(
        scope_type=fixture["scope_type"],
        scope_id=fixture["scope_id"],
        type=fixture["archived"]["type"],
        content=fixture["archived"]["content"],
        created_by="eval",
    )
    await memory.archive_shared_memory(archived.id)
    results = await memory.search_shared_memory(
        fixture["scope_type"],
        fixture["scope_id"],
        "archived",
    )
    assert archived.id not in {result.id for result in results}

    proposal = reflection.create_memory_maintenance_proposal(
        user_id="owner",
        action="suggest_shared_memory_or_kb",
        target_memory_ids=[],
        proposed_content=fixture["proposal"]["content"],
        risk="medium",
        reason="Evaluation proposal.",
        evidence_ids=["eval-trace"],
        metadata_patch={
            "target": "shared_memory",
            "scope_type": fixture["scope_type"],
            "scope_id": fixture["scope_id"],
            "type": fixture["proposal"]["type"],
        },
    )
    reflection.approve_memory_maintenance_proposal(proposal.id, actor_user_id="owner")
    applied = await memory.apply_shared_memory_proposal(proposal.id, actor_id="owner")
    results = await memory.search_shared_memory(
        fixture["scope_type"], fixture["scope_id"], "github"
    )

    assert applied.id in {result.id for result in results}
