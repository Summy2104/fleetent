import pytest

from fleetent.intelligence.memory import maintenance
from tests.integration.test_migrations import apply_migrations


def _patch_database(tmp_path, monkeypatch):
    db_path = tmp_path / "memory-retention.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    return db_path


def _insert_memory(
    db_path,
    *,
    id: str,
    user_id: str = "user-1",
    type: str = "identity",
    content: str = "User likes Python",
    updated_at: str = "2026-01-01T00:00:00+00:00",
    expires_at: str | None = None,
) -> None:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO memory_items (
                id, user_id, type, content, created_at, updated_at, expires_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, user_id, type, content, updated_at, updated_at, expires_at),
        )


def _memory_ids(db_path) -> list[str]:
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        return [row[0] for row in conn.execute("SELECT id FROM memory_items ORDER BY id")]


def test_memory_maintenance_public_api_is_importable():
    from fleetent.intelligence.memory import (
        MemoryCompactionCandidate,
        MemoryMaintenancePolicy,
        MemoryMaintenanceSummary,
        run_memory_maintenance,
    )

    assert MemoryCompactionCandidate
    assert MemoryMaintenancePolicy
    assert MemoryMaintenanceSummary
    assert callable(run_memory_maintenance)


@pytest.mark.parametrize(
    "policy_kwargs",
    [
        {"max_identity": -1},
        {"max_preferences": -1},
        {"max_context": -1},
    ],
)
async def test_memory_maintenance_rejects_negative_limits(policy_kwargs):
    from fleetent.intelligence.memory import MemoryMaintenancePolicy, run_memory_maintenance

    with pytest.raises(ValueError, match="must be greater than or equal to 0"):
        await run_memory_maintenance(
            "user-1",
            policy=MemoryMaintenancePolicy(**policy_kwargs),
            dry_run=True,
        )


async def test_memory_maintenance_rejects_empty_user_id():
    from fleetent.intelligence.memory import MemoryMaintenancePolicy, run_memory_maintenance

    with pytest.raises(ValueError, match="user_id must not be empty"):
        await run_memory_maintenance("", policy=MemoryMaintenancePolicy(), dry_run=True)


async def test_dry_run_reports_expired_context_without_deleting_sqlite_or_vectors(
    tmp_path, monkeypatch
):
    from fleetent.intelligence import memory as memory_layer

    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory(
        db_path,
        id="ctx-expired",
        type="context",
        content="User is working on old billing migration",
        expires_at="2026-01-01T00:00:00+00:00",
    )
    vector_deletes = []

    async def delete_vector(id: str, namespace: str) -> None:
        vector_deletes.append((id, namespace))

    monkeypatch.setattr(maintenance.vector_store, "delete", delete_vector)

    summary = await memory_layer.run_memory_maintenance(
        "user-1",
        policy=memory_layer.MemoryMaintenancePolicy(),
        dry_run=True,
    )

    assert summary.expired_count == 1
    assert summary.deleted_ids == ["ctx-expired"]
    assert _memory_ids(db_path) == ["ctx-expired"]
    assert vector_deletes == []


async def test_dry_run_reports_over_limit_rows_without_deleting_sqlite_or_vectors(
    tmp_path, monkeypatch
):
    from fleetent.intelligence import memory as memory_layer

    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory(
        db_path,
        id="pref-new",
        type="preferences",
        content="User prefers concise answers",
        updated_at="2026-01-03T00:00:00+00:00",
    )
    _insert_memory(
        db_path,
        id="pref-old",
        type="preferences",
        content="User prefers verbose answers",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    vector_deletes = []

    async def delete_vector(id: str, namespace: str) -> None:
        vector_deletes.append((id, namespace))

    monkeypatch.setattr(maintenance.vector_store, "delete", delete_vector)

    summary = await memory_layer.run_memory_maintenance(
        "user-1",
        policy=memory_layer.MemoryMaintenancePolicy(max_preferences=1),
        dry_run=True,
    )

    assert summary.over_limit_count == 1
    assert summary.deleted_ids == ["pref-old"]
    assert _memory_ids(db_path) == ["pref-new", "pref-old"]
    assert vector_deletes == []


async def test_duplicate_compaction_candidate_groups_same_user_type_normalized_content(
    tmp_path, monkeypatch
):
    from fleetent.intelligence import memory as memory_layer

    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory(
        db_path,
        id="pref-canonical",
        type="preferences",
        content="User prefers concise answers",
        updated_at="2026-01-03T00:00:00+00:00",
    )
    _insert_memory(
        db_path,
        id="pref-duplicate",
        type="preferences",
        content="  user   prefers concise answers  ",
        updated_at="2026-01-01T00:00:00+00:00",
    )

    summary = await memory_layer.run_memory_maintenance(
        "user-1",
        policy=memory_layer.MemoryMaintenancePolicy(compact_duplicates=True),
        dry_run=True,
    )

    assert summary.compaction_candidates == [
        memory_layer.MemoryCompactionCandidate(
            type="preferences",
            canonical_id="pref-canonical",
            duplicate_ids=["pref-duplicate"],
            reason="duplicate_normalized_content",
        )
    ]
    assert summary.compacted_count == 1
    assert _memory_ids(db_path) == ["pref-canonical", "pref-duplicate"]


async def test_duplicate_compaction_uses_id_as_tie_breaker_for_newest_rows(tmp_path, monkeypatch):
    from fleetent.intelligence import memory as memory_layer

    db_path = _patch_database(tmp_path, monkeypatch)
    _insert_memory(
        db_path,
        id="pref-a",
        type="preferences",
        content="User prefers concise answers",
        updated_at="2026-01-03T00:00:00+00:00",
    )
    _insert_memory(
        db_path,
        id="pref-b",
        type="preferences",
        content="User prefers concise answers",
        updated_at="2026-01-03T00:00:00+00:00",
    )

    summary = await memory_layer.run_memory_maintenance(
        "user-1",
        policy=memory_layer.MemoryMaintenancePolicy(compact_duplicates=True),
        dry_run=True,
    )

    [candidate] = summary.compaction_candidates
    assert candidate.canonical_id == "pref-a"
    assert candidate.duplicate_ids == ["pref-b"]
