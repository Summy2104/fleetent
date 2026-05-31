from dataclasses import dataclass
from datetime import UTC, datetime

from fleetent.db import Row, SQLiteDatabase


@dataclass(frozen=True)
class LocalSourceState:
    """Stored fingerprint for a local source document."""

    source_id: str
    tenant_id: str
    kb_id: str
    source_path: str
    mtime_ns: int
    content_hash: str
    document_id: str


class LocalSourceStateStore:
    """Database boundary for local connector source-state rows."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def upsert(self, state: LocalSourceState) -> None:
        with self._database.transaction() as transaction:
            transaction.execute(
                """
                DELETE FROM knowledge_source_states
                WHERE source_id = :source_id
                  AND tenant_id = :tenant_id
                  AND kb_id = :kb_id
                  AND source_path = :source_path
                """,
                {
                    "source_id": state.source_id,
                    "tenant_id": state.tenant_id,
                    "kb_id": state.kb_id,
                    "source_path": state.source_path,
                },
            )
            transaction.execute(
                """
                INSERT INTO knowledge_source_states (
                    source_id, tenant_id, kb_id, source_path, mtime_ns, content_hash,
                    document_id, updated_at
                )
                VALUES (
                    :source_id, :tenant_id, :kb_id, :source_path, :mtime_ns, :content_hash,
                    :document_id, :updated_at
                )
                """,
                {
                    "source_id": state.source_id,
                    "tenant_id": state.tenant_id,
                    "kb_id": state.kb_id,
                    "source_path": state.source_path,
                    "mtime_ns": state.mtime_ns,
                    "content_hash": state.content_hash,
                    "document_id": state.document_id,
                    "updated_at": _format_datetime(_now()),
                },
            )

    def get(
        self,
        source_id: str,
        tenant_id: str,
        kb_id: str,
        source_path: str,
    ) -> LocalSourceState | None:
        row = self._database.execute(
            """
            SELECT source_id, tenant_id, kb_id, source_path, mtime_ns, content_hash, document_id
            FROM knowledge_source_states
            WHERE source_id = :source_id
              AND tenant_id = :tenant_id
              AND kb_id = :kb_id
              AND source_path = :source_path
            """,
            {
                "source_id": source_id,
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "source_path": source_path,
            },
        ).fetchone()
        if row is None:
            return None
        return _row_to_state(row)

    def is_unchanged(
        self,
        source_id: str,
        tenant_id: str,
        kb_id: str,
        source_path: str,
        mtime_ns: int,
        content_hash: str,
    ) -> bool:
        state = self.get(source_id, tenant_id, kb_id, source_path)
        return (
            state is not None and state.mtime_ns == mtime_ns and state.content_hash == content_hash
        )


def _row_to_state(row: Row) -> LocalSourceState:
    return LocalSourceState(
        source_id=str(row["source_id"]),
        tenant_id=str(row["tenant_id"]),
        kb_id=str(row["kb_id"]),
        source_path=str(row["source_path"]),
        mtime_ns=int(row["mtime_ns"]),
        content_hash=str(row["content_hash"]),
        document_id=str(row["document_id"]),
    )


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _format_datetime(value: datetime) -> str:
    return value.isoformat()
