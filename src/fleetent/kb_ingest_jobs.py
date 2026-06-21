"""Management-DB backed KB ingest job queue."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fleetent.config import Settings
from fleetent.db import SQLiteDatabase, create_database

_RESULT_KEY = "__result__"
_REQUEST_KEY = "__request__"


def _database() -> SQLiteDatabase:
    return create_database(Settings().database_url)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _decode(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    job = dict(row)
    job["attempts"] = int(job["attempts"])
    job["max_attempts"] = int(job["max_attempts"])
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    row = (
        _database()
        .execute(
            "SELECT * FROM kb_ingest_jobs WHERE id = :id",
            {"id": job_id},
        )
        .fetchone()
    )
    return _decode(row)


def get_job_payload(job: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(str(job["connector_ref"]))
    if _REQUEST_KEY in payload and isinstance(payload[_REQUEST_KEY], dict):
        return dict(payload[_REQUEST_KEY])
    return payload


def get_job_result(job: dict[str, Any]) -> dict[str, Any] | None:
    payload = json.loads(str(job["connector_ref"]))
    result = payload.get(_RESULT_KEY)
    if isinstance(result, dict):
        return dict(result)
    return None


def enqueue_job(
    *,
    job_type: str,
    tenant_id: str,
    kb_id: str,
    connector_ref: dict[str, Any],
    cred_ref: str = "",
    max_attempts: int = 3,
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    now = _now()
    payload = {
        "id": job_id,
        "job_type": job_type,
        "tenant_id": tenant_id,
        "kb_id": kb_id,
        "connector_ref": json.dumps(connector_ref),
        "cred_ref": cred_ref,
        "status": "pending",
        "attempts": 0,
        "max_attempts": max_attempts,
        "last_error": None,
        "created_at": now,
        "updated_at": now,
        "claimed_at": None,
        "finished_at": None,
    }
    with _database().transaction() as conn:
        conn.execute(
            """
            INSERT INTO kb_ingest_jobs (
                id, job_type, tenant_id, kb_id, connector_ref, cred_ref, status,
                attempts, max_attempts, last_error, created_at, updated_at, claimed_at, finished_at
            ) VALUES (
                :id, :job_type, :tenant_id, :kb_id, :connector_ref, :cred_ref, :status,
                :attempts, :max_attempts, :last_error, :created_at, :updated_at,
                :claimed_at, :finished_at
            )
            """,
            payload,
        )
    return payload


def enqueue_connector_job(
    connector_row: dict[str, Any],
    *,
    max_attempts: int = 3,
) -> dict[str, Any]:
    config = dict(connector_row.get("config") or {})
    cred_ref = str(config.pop("credential_ref", "") or "")
    if not cred_ref and connector_row.get("kind") == "confluence":
        api_token_env = str(config.pop("api_token_env", "") or "")
        if api_token_env:
            cred_ref = f"env:{api_token_env}"
    connector_ref = {
        "connector_id": connector_row["connector_id"],
        "kind": connector_row["kind"],
        "config": config,
    }
    return enqueue_job(
        job_type="connector_sync",
        tenant_id=str(connector_row["tenant_id"]),
        kb_id=str(connector_row["kb_id"]),
        connector_ref=connector_ref,
        cred_ref=cred_ref,
        max_attempts=max_attempts,
    )


def claim_job(job_id: str) -> dict[str, Any] | None:
    now = _now()
    with _database().transaction() as conn:
        row = conn.execute(
            """
            UPDATE kb_ingest_jobs
            SET status = 'claimed', claimed_at = :now, updated_at = :now
            WHERE id = :id AND status = 'pending'
            RETURNING *
            """,
            {"id": job_id, "now": now},
        ).fetchone()
    return _decode(row)


def claim_next_job() -> dict[str, Any] | None:
    now = _now()
    with _database().transaction() as conn:
        row = conn.execute(
            """
            UPDATE kb_ingest_jobs
            SET status = 'claimed', claimed_at = :now, updated_at = :now
            WHERE id = (
                SELECT id
                FROM kb_ingest_jobs
                WHERE status = 'pending'
                ORDER BY created_at, id
                LIMIT 1
            )
            RETURNING *
            """,
            {"now": now},
        ).fetchone()
    return _decode(row)


def mark_done(job_id: str, *, result: dict[str, Any] | None = None) -> dict[str, Any] | None:
    now = _now()
    with _database().transaction() as conn:
        current = conn.execute(
            "SELECT connector_ref FROM kb_ingest_jobs WHERE id = :id",
            {"id": job_id},
        ).fetchone()
        if current is None:
            return None
        connector_ref = str(current["connector_ref"])
        if result is not None:
            connector_ref = json.dumps(
                {
                    _REQUEST_KEY: json.loads(connector_ref),
                    _RESULT_KEY: result,
                }
            )
        row = conn.execute(
            """
            UPDATE kb_ingest_jobs
            SET status = 'done',
                connector_ref = :connector_ref,
                updated_at = :now,
                finished_at = :now
            WHERE id = :id
            RETURNING *
            """,
            {"id": job_id, "connector_ref": connector_ref, "now": now},
        ).fetchone()
    return _decode(row)


def mark_failed(job_id: str, error: str) -> dict[str, Any] | None:
    with _database().transaction() as conn:
        current = conn.execute(
            "SELECT attempts, max_attempts FROM kb_ingest_jobs WHERE id = :id",
            {"id": job_id},
        ).fetchone()
        if current is None:
            return None
        attempts = int(current["attempts"]) + 1
        max_attempts = int(current["max_attempts"])
        now = _now()
        if attempts >= max_attempts:
            row = conn.execute(
                """
                UPDATE kb_ingest_jobs
                SET status = 'failed',
                    attempts = :attempts,
                    last_error = :error,
                    updated_at = :now,
                    finished_at = :now
                WHERE id = :id
                RETURNING *
                """,
                {"id": job_id, "attempts": attempts, "error": error, "now": now},
            ).fetchone()
        else:
            row = conn.execute(
                """
                UPDATE kb_ingest_jobs
                SET status = 'pending',
                    attempts = :attempts,
                    last_error = :error,
                    updated_at = :now,
                    claimed_at = NULL,
                    finished_at = NULL
                WHERE id = :id
                RETURNING *
                """,
                {"id": job_id, "attempts": attempts, "error": error, "now": now},
            ).fetchone()
    return _decode(row)
