import json
from pathlib import Path

from fleetent.db import create_database
from fleetent.vector_store import SearchResult

FIXTURE = Path("tests/evaluation/fixtures/shared_memory/basic.json")


async def test_agent_memory_evaluation_covers_create_archive_and_proposal_apply(
    monkeypatch, tmp_path
):
    from fleetent import memory, reflection
    from fleetent.db import SQLiteDatabase
    from fleetent.memory import agent_memory as agent_memory_module
    from fleetent.memory import store
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.schema_migrations import migrate
    from tests.integration.test_migrations import apply_migrations

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    db_path = tmp_path / "agent-memory-eval.db"
    agent_db_path = tmp_path / "agent-memory.db"
    apply_migrations(db_path)
    database = create_database(f"sqlite:///{db_path}")
    agent_db = SQLiteDatabase(path=agent_db_path)
    migrate(agent_db, AGENT_STATE_MIGRATIONS)
    monkeypatch.setattr(store, "database", lambda: database)
    monkeypatch.setattr(reflection, "_database", lambda: database)
    monkeypatch.setattr(reflection.observability, "record_trace_event", lambda event: None)
    monkeypatch.setattr(agent_memory_module, "_agent_memory_db", agent_db)

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

    monkeypatch.setattr(agent_memory_module.vector_store, "upsert", upsert)
    monkeypatch.setattr(agent_memory_module.vector_store, "delete", delete)
    monkeypatch.setattr(agent_memory_module.vector_store, "search", search)

    for item in fixture["items"]:
        created = await memory.create_agent_memory(
            type=item["type"],
            content=item["content"],
            created_by="eval",
        )
        results = await memory.search_agent_memory(item["expected_query"])
        assert created.id in {result.id for result in results}

    archived = await memory.create_agent_memory(
        type=fixture["archived"]["type"],
        content=fixture["archived"]["content"],
        created_by="eval",
    )
    await memory.archive_agent_memory(archived.id)
    results = await memory.search_agent_memory("archived")
    assert archived.id not in {result.id for result in results}

    proposal = reflection.create_memory_maintenance_proposal(
        user_id="owner",
        action="suggest_agent_memory_or_kb",
        target_memory_ids=[],
        proposed_content=fixture["proposal"]["content"],
        risk="medium",
        reason="Evaluation proposal.",
        evidence_ids=["eval-trace"],
        metadata_patch={
            "target": "agent_memory",
            "type": fixture["proposal"]["type"],
        },
    )
    reflection.approve_memory_maintenance_proposal(proposal.id, actor_user_id="owner")
    applied = await memory.apply_agent_memory_proposal(proposal.id, actor_id="owner")
    results = await memory.search_agent_memory("github")

    assert applied.id in {result.id for result in results}
