import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Protocol
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


_MILVUS_COLLECTION = "fleetent_vectors"
# One collection holds every namespace, so the key has to carry both parts: the SQLite backend's
# key is (namespace, id), and folding that onto Milvus's single primary-key field would let a
# write in one tenant's namespace overwrite another's row. \x1f cannot occur in either part.
_MILVUS_KEY_SEPARATOR = "\x1f"
_MILVUS_MAX_KEY_LENGTH = 1024
_MILVUS_MAX_FIELD_LENGTH = 512


@dataclass(frozen=True)
class MilvusVectorBackend:
    """Milvus-backed vector store, embedded (Milvus Lite) or remote, chosen by URI.

    ``milvus:///path/to/file.db`` runs Milvus Lite in-process — no Docker, which is what makes
    this usable on a developer machine; an ``http(s)://host:port`` url talks to a Milvus cluster
    through the same client, so switching between them is a config change rather than a code
    change.

    Namespaces (``kb:{tenant}:{kb_id}``, ``mem:{user}``) cannot be collection names — the colons
    are illegal — so isolation rides on a partition-key field: Milvus groups rows physically by
    its hash, and every read additionally filters on it. The filter is what guarantees isolation;
    the partition key is what keeps the scan from crossing tenants.

    Stateless like ``SQLiteVectorBackend``: a client is built per call. pymilvus keeps one
    embedded server per path internally, so only the first call in a process pays startup.
    """

    database_url: str

    def __post_init__(self) -> None:
        _resolve_milvus_uri(self.database_url)

    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        if not vector:
            raise ValueError("vector must not be empty")

        await _to_thread(self._upsert_sync, id, vector, namespace)

    async def search(
        self, vector: list[float], namespace: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []

        return await _to_thread(self._search_sync, vector, namespace, limit)

    async def delete(self, id: str, namespace: str) -> None:
        await _to_thread(self._delete_sync, id, namespace)

    async def clear_namespace(self, namespace: str) -> None:
        await _to_thread(self._clear_namespace_sync, namespace)

    # ── synchronous bodies (pymilvus has no async client) ──

    def _client(self) -> Any:
        from pymilvus import MilvusClient  # type: ignore[import-untyped]

        uri = _resolve_milvus_uri(self.database_url)
        if not uri.startswith(("http://", "https://")):
            Path(uri).parent.mkdir(parents=True, exist_ok=True)
        return MilvusClient(uri)

    def _upsert_sync(self, id: str, vector: list[float], namespace: str) -> None:
        client = self._client()
        self._ensure_collection(client, dimensions=len(vector))
        client.upsert(
            _MILVUS_COLLECTION,
            data=[
                {
                    "pk": _milvus_key(namespace, id),
                    "namespace": namespace,
                    "chunk_id": id,
                    "vector": vector,
                }
            ],
        )

    def _search_sync(self, vector: list[float], namespace: str, limit: int) -> list[SearchResult]:
        client = self._client()
        if not client.has_collection(_MILVUS_COLLECTION):
            return []

        hits = client.search(
            _MILVUS_COLLECTION,
            data=[vector],
            limit=limit,
            filter=_namespace_filter(namespace),
            output_fields=["chunk_id"],
        )
        results = [
            SearchResult(id=hit["entity"]["chunk_id"], score=float(hit["distance"]))
            for hit in (hits[0] if hits else [])
        ]
        # Milvus already returns descending distance; re-sorting pins the id tie-break so the
        # ordering contract matches the other backends exactly.
        return sorted(results, key=lambda result: (-result.score, result.id))[:limit]

    def _delete_sync(self, id: str, namespace: str) -> None:
        client = self._client()
        if not client.has_collection(_MILVUS_COLLECTION):
            return
        client.delete(_MILVUS_COLLECTION, ids=[_milvus_key(namespace, id)])

    def _clear_namespace_sync(self, namespace: str) -> None:
        client = self._client()
        if not client.has_collection(_MILVUS_COLLECTION):
            return
        client.delete(_MILVUS_COLLECTION, filter=_namespace_filter(namespace))

    def _ensure_collection(self, client: Any, dimensions: int) -> None:
        from pymilvus import DataType

        if client.has_collection(_MILVUS_COLLECTION):
            existing = _collection_dimensions(client)
            if existing is not None and existing != dimensions:
                raise ValueError(
                    f"Milvus collection {_MILVUS_COLLECTION!r} has vector dimension {existing}, "
                    f"got {dimensions}. Reindex the namespace instead of mixing widths."
                )
            return

        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("pk", DataType.VARCHAR, is_primary=True, max_length=_MILVUS_MAX_KEY_LENGTH)
        schema.add_field(
            "namespace",
            DataType.VARCHAR,
            max_length=_MILVUS_MAX_FIELD_LENGTH,
            is_partition_key=True,
        )
        schema.add_field("chunk_id", DataType.VARCHAR, max_length=_MILVUS_MAX_FIELD_LENGTH)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dimensions)

        index_params = client.prepare_index_params()
        # AUTOINDEX lets Milvus Lite fall back to a flat scan while a real cluster picks HNSW/IVF
        # for the same declaration; COSINE matches the similarity the other backends report.
        index_params.add_index(field_name="vector", index_type="AUTOINDEX", metric_type="COSINE")
        client.create_collection(_MILVUS_COLLECTION, schema=schema, index_params=index_params)


def _milvus_key(namespace: str, id: str) -> str:
    return f"{namespace}{_MILVUS_KEY_SEPARATOR}{id}"


def _namespace_filter(namespace: str) -> str:
    if '"' in namespace or "\\" in namespace:
        raise ValueError(f"namespace must not contain quotes or backslashes: {namespace!r}")
    return f'namespace == "{namespace}"'


def _collection_dimensions(client: Any) -> int | None:
    for field in client.describe_collection(_MILVUS_COLLECTION).get("fields", []):
        if field.get("name") == "vector":
            dim = field.get("params", {}).get("dim")
            return int(dim) if dim is not None else None
    return None


def _resolve_milvus_uri(database_url: str) -> str:
    """Translate a configured url into a pymilvus uri.

    ``milvus:///abs/path.db`` selects embedded Milvus Lite; an http(s) url selects a remote
    cluster. Anything else is rejected here rather than deep inside pymilvus, so a typo surfaces
    at construction time.
    """
    if not database_url.strip():
        raise ValueError("milvus vector backend requires a non-empty database_url")
    if database_url.startswith(("http://", "https://")):
        return database_url
    if database_url.startswith("milvus://"):
        path = unquote(urlparse(database_url).path)
        if not path:
            raise ValueError(f"milvus url is missing a database path: {database_url!r}")
        return path
    raise ValueError(
        f"Unsupported milvus database_url {database_url!r}. "
        "Use milvus:///path/to/file.db for embedded Milvus Lite or http(s)://host:port for a "
        "remote cluster."
    )


async def _to_thread[T](func: Callable[..., T], *args: object) -> T:
    """Run a blocking pymilvus call off the event loop."""
    import anyio.to_thread

    return await anyio.to_thread.run_sync(partial(func, *args))


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
    if settings.backend == "milvus":
        if database_url is None:
            raise ValueError("milvus vector backend requires a database_url")
        return MilvusVectorBackend(database_url=database_url)
    raise ValueError(
        f"Unsupported vector_store.backend {settings.backend!r}. "
        "Supported vector backends: memory, sqlite, milvus"
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
