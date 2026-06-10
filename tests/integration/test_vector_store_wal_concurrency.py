"""Integration tests: SQLiteVectorBackend must apply WAL + busy_timeout on every connection.

Scenarios (from spec vector-store/spec.md):
  1. journal_mode=wal after any backend operation (file-level, persistent)
  2. busy_timeout is non-zero (verified via module constant)
  3. Concurrent read + write — read must not get "database is locked"
  4. Two near-simultaneous writers — second must wait and succeed within busy_timeout
"""

import asyncio

import aiosqlite


def _db_url(tmp_path, name: str = "vectors.db") -> str:
    return f"sqlite:///{tmp_path / name}"


async def test_connection_enables_wal_journal_mode(tmp_path):
    """WAL mode is set (persistent file-level) after first backend operation."""
    from fleetent.vector_store.backend import SQLiteVectorBackend

    backend = SQLiteVectorBackend(database_url=_db_url(tmp_path))
    await backend.upsert("a", [1.0, 0.0], namespace="ns")

    db_path = tmp_path / "vectors.db"
    async with aiosqlite.connect(db_path) as db:
        rows = await db.execute_fetchall("PRAGMA journal_mode")
        assert rows[0][0] == "wal", f"expected wal, got {rows[0][0]!r}"


async def test_busy_timeout_constant_is_nonzero():
    """_VECTOR_WAL_BUSY_TIMEOUT_MS must be positive so SQLite retries on busy."""
    from fleetent.vector_store.backend import _VECTOR_WAL_BUSY_TIMEOUT_MS

    assert _VECTOR_WAL_BUSY_TIMEOUT_MS > 0


async def test_concurrent_read_does_not_fail_while_writing(tmp_path):
    """With WAL, a concurrent read must succeed while a write is in progress."""
    from fleetent.vector_store.backend import SQLiteVectorBackend

    backend = SQLiteVectorBackend(database_url=_db_url(tmp_path))
    await backend.upsert("seed", [1.0, 0.0], namespace="ns")

    async def write_many() -> None:
        for i in range(10):
            await backend.upsert(f"w-{i}", [float(i), 0.0], namespace="ns")

    async def read_concurrently() -> list:
        return await backend.search([1.0, 0.0], namespace="ns", limit=5)

    # asyncio.gather exercises concurrent scheduling; WAL must not lock the reader
    write_task = asyncio.create_task(write_many())
    read_task = asyncio.create_task(read_concurrently())
    results, _ = await asyncio.gather(read_task, write_task)
    assert isinstance(results, list)  # did not raise OperationalError


async def test_two_concurrent_writers_succeed_within_busy_timeout(tmp_path):
    """Second writer must wait and succeed, not fail immediately with database is locked.

    A direct aiosqlite connection holds an EXCLUSIVE transaction for ~50 ms.
    The backend upsert waits up to busy_timeout (5 s) and succeeds.
    Without busy_timeout the upsert would fail immediately.
    """
    from fleetent.vector_store.backend import SQLiteVectorBackend

    db_url = _db_url(tmp_path)
    backend = SQLiteVectorBackend(database_url=db_url)
    # Ensure schema and WAL are initialised before the lock test.
    await backend.upsert("seed", [0.5, 0.5], namespace="ns")

    db_path = tmp_path / "vectors.db"

    async def hold_exclusive_lock() -> None:
        async with aiosqlite.connect(db_path) as db:
            await db.execute("BEGIN EXCLUSIVE")
            await asyncio.sleep(0.05)  # hold for 50 ms
            await db.execute("ROLLBACK")

    async def write_via_backend() -> None:
        # Small delay so the lock holder starts first.
        await asyncio.sleep(0.01)
        await backend.upsert("new", [1.0, 0.0], namespace="ns")

    # Both must complete: the backend waits up to busy_timeout and retries.
    await asyncio.gather(hold_exclusive_lock(), write_via_backend())

    results = await backend.search([1.0, 0.0], namespace="ns")
    assert any(r.id == "new" for r in results)
