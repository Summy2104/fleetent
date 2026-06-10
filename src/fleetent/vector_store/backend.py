import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse

import aiosqlite

from fleetent.config import VectorStoreSettings

# Must match db.py _WAL_BUSY_TIMEOUT_MS so all SQLite connections share the same retry window.
_VECTOR_WAL_BUSY_TIMEOUT_MS = 5000


@dataclass(frozen=True)
class SearchResult:
    id: str
    score: float


class VectorBackend(Protocol):
    async def upsert(self, id: str, vector: list[float], namespace: str) -> None: ...

    async def search(
        self, vector: list[float], namespace: str, limit: int = 10
    ) -> list[SearchResult]: ...

    async def delete(self, id: str, namespace: str) -> None: ...

    async def clear_namespace(self, namespace: str) -> None: ...


@dataclass(frozen=True)
class SQLiteVectorBackend:
    database_url: str

    def __post_init__(self) -> None:
        _validate_local_sqlite_url(self.database_url)

    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        if not vector:
            raise ValueError("vector must not be empty")

        database_path = _sqlite_path(self.database_url)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        async with _connect(database_path) as db:
            await _init_sqlite_schema(db)
            await db.execute(
                """
                INSERT INTO vector_items (namespace, id, dimensions, vector_json, updated_at)
                VALUES (:namespace, :id, :dimensions, :vector_json, CURRENT_TIMESTAMP)
                ON CONFLICT(namespace, id) DO UPDATE SET
                    dimensions = excluded.dimensions,
                    vector_json = excluded.vector_json,
                    updated_at = excluded.updated_at
                """,
                {
                    "namespace": namespace,
                    "id": id,
                    "dimensions": len(vector),
                    "vector_json": json.dumps(vector),
                },
            )
            await db.commit()

    async def search(
        self, vector: list[float], namespace: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []

        database_path = _sqlite_path(self.database_url)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        async with _connect(database_path) as db:
            db.row_factory = aiosqlite.Row
            await _init_sqlite_schema(db)
            rows = await db.execute_fetchall(
                """
                SELECT id, dimensions, vector_json
                FROM vector_items
                WHERE namespace = :namespace
                """,
                {"namespace": namespace},
            )

        results: list[SearchResult] = []
        for row in rows:
            if row["dimensions"] != len(vector):
                continue
            stored_vector = _load_vector(row["vector_json"])
            if stored_vector is None or len(stored_vector) != len(vector):
                continue
            results.append(SearchResult(id=row["id"], score=_similarity(vector, stored_vector)))
        return sorted(results, key=lambda result: (-result.score, result.id))[:limit]

    async def delete(self, id: str, namespace: str) -> None:
        database_path = _sqlite_path(self.database_url)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        async with _connect(database_path) as db:
            await _init_sqlite_schema(db)
            await db.execute(
                """
                DELETE FROM vector_items
                WHERE namespace = :namespace AND id = :id
                """,
                {"namespace": namespace, "id": id},
            )
            await db.commit()

    async def clear_namespace(self, namespace: str) -> None:
        database_path = _sqlite_path(self.database_url)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        async with _connect(database_path) as db:
            await _init_sqlite_schema(db)
            await db.execute(
                """
                DELETE FROM vector_items
                WHERE namespace = :namespace
                """,
                {"namespace": namespace},
            )
            await db.commit()


class InMemoryVectorBackend:
    def __init__(self) -> None:
        self._vectors: dict[str, dict[str, list[float]]] = {}

    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        self._vectors.setdefault(namespace, {})[id] = vector

    async def search(
        self, vector: list[float], namespace: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []

        results = [
            SearchResult(id=id, score=_similarity(vector, stored_vector))
            for id, stored_vector in self._vectors.get(namespace, {}).items()
        ]
        return sorted(results, key=lambda result: (-result.score, result.id))[:limit]

    async def delete(self, id: str, namespace: str) -> None:
        self._vectors.get(namespace, {}).pop(id, None)

    async def clear_namespace(self, namespace: str) -> None:
        self._vectors.pop(namespace, None)


def _similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    score = sum(
        left_value * right_value for left_value, right_value in zip(left, right, strict=True)
    ) / (left_norm * right_norm)
    return float(max(0.0, min(1.0, score)))


def create_vector_backend(
    settings: VectorStoreSettings, database_url: str | None = None
) -> VectorBackend:
    if settings.backend == "memory":
        return InMemoryVectorBackend()
    if settings.backend == "sqlite":
        if database_url is None:
            raise ValueError("sqlite vector backend requires a local sqlite database_url")
        return SQLiteVectorBackend(database_url=database_url)
    raise ValueError(
        f"Unsupported vector_store.backend {settings.backend!r}. "
        "Supported vector backends: memory, sqlite"
    )


@asynccontextmanager
async def _connect(path: Path) -> AsyncIterator[aiosqlite.Connection]:
    """Open an aiosqlite connection with WAL journal mode and busy_timeout set."""
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute(f"PRAGMA busy_timeout={_VECTOR_WAL_BUSY_TIMEOUT_MS}")
        yield db


def _validate_local_sqlite_url(database_url: str) -> None:
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite" or parsed.netloc not in {"", "localhost"}:
        raise ValueError("sqlite vector backend requires a local sqlite database_url")


def _sqlite_path(database_url: str) -> Path:
    parsed = urlparse(database_url)
    raw_path = unquote(parsed.path)
    if database_url.startswith("sqlite:////") and raw_path.startswith("//"):
        raw_path = raw_path[1:]
    if database_url.startswith("sqlite:///") and not database_url.startswith("sqlite:////"):
        raw_path = raw_path.lstrip("/")
    return Path(raw_path)


async def _init_sqlite_schema(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS vector_items (
            namespace TEXT NOT NULL,
            id TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            vector_json TEXT NOT NULL,
            updated_at DATETIME NOT NULL,
            UNIQUE(namespace, id)
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_vector_items_namespace
        ON vector_items(namespace)
        """
    )


def _load_vector(vector_json: str) -> list[float] | None:
    try:
        value = json.loads(vector_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, list):
        return None
    vector: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int | float):
            return None
        vector.append(float(item))
    return vector
