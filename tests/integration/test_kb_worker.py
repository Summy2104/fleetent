import json

import pytest

from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from tests.integration._migration_template import apply_migrations


def _prepare_management_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")


def test_run_once_marks_import_job_done_and_writes_kb(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _prepare_management_db(tmp_path, monkeypatch)

    from fleetent import kb_ingest_jobs, vector_store
    from fleetent.knowledge_base import worker
    from fleetent.knowledge_base.management.runtime import create_knowledge_base

    async def embed_text(text: str) -> list[float]:
        return [float(len(text)), 0.0]

    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    create_knowledge_base(
        "tenant-a",
        "handbook",
        "Support handbook",
        database=worker._knowledge_database("tenant-a"),
    )

    job = kb_ingest_jobs.enqueue_job(
        job_type="import_document",
        tenant_id="tenant-a",
        kb_id="handbook",
        connector_ref={
            "source": "guide.md",
            "content": "# Intro\nRunbook",
            "document_format": "markdown",
        },
    )

    result = worker.run_once()

    assert result == {"job_id": job["id"], "status": "done"}
    stored = kb_ingest_jobs.get_job(job["id"])
    assert stored is not None
    assert stored["status"] == "done"

    kb_db = worker._tenant_router().tenant_scope("tenant-a").open_kb_db(KB_MIGRATIONS)
    rows = kb_db.execute(
        """
        SELECT kb_id, filename, source
        FROM knowledge_documents
        ORDER BY created_at ASC
        """
    ).fetchall()
    assert rows == [{"kb_id": "handbook", "filename": "guide.md", "source": "guide.md"}]


def test_run_once_retries_failed_job_until_max_attempts(tmp_path, monkeypatch: pytest.MonkeyPatch):
    _prepare_management_db(tmp_path, monkeypatch)

    from fleetent import kb_ingest_jobs
    from fleetent.knowledge_base import worker

    job = kb_ingest_jobs.enqueue_job(
        job_type="unknown_job",
        tenant_id="tenant-a",
        kb_id="handbook",
        connector_ref={},
        max_attempts=2,
    )

    first = worker.run_once()
    assert first == {"job_id": job["id"], "status": "pending"}

    retried = kb_ingest_jobs.get_job(job["id"])
    assert retried is not None
    assert retried["status"] == "pending"
    assert retried["attempts"] == 1

    second = worker.run_once()
    assert second == {"job_id": job["id"], "status": "failed"}

    failed = kb_ingest_jobs.get_job(job["id"])
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["attempts"] == 2
    assert "unknown kb ingest job type" in str(failed["last_error"])


def test_run_job_injects_connector_settings_for_standalone_sync(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    _prepare_management_db(tmp_path, monkeypatch)

    from fleetent.knowledge_base import operations, worker

    captured: dict[str, object] = {}

    async def fake_run_connector_sync(connector_id, *, settings, dry_run):
        captured["connector_id"] = connector_id
        captured["settings"] = settings
        captured["dry_run"] = dry_run
        return operations.ConnectorSyncResult(
            connector_id=connector_id,
            status="sync_succeeded",
            summary={"planned": 1},
        )

    monkeypatch.setattr(worker.knowledge_base, "run_connector_sync", fake_run_connector_sync)
    job = {
        "job_type": "connector_sync",
        "tenant_id": "tenant-a",
        "kb_id": "kb-a",
        "cred_ref": "file:///secure/google.json",
        "connector_ref": json.dumps(
            {
                "connector_id": "drive-sync",
                "kind": "google_drive",
                "config": {"folder_id": "folder-123"},
            }
        ),
    }

    result = worker.run_job(job)

    assert result == {
        "connector_id": "drive-sync",
        "status": "sync_succeeded",
        "summary": {"planned": 1},
        "error": None,
    }
    settings = captured["settings"]
    assert captured["connector_id"] == "drive-sync"
    assert captured["dry_run"] is False
    assert settings.google_drive.connectors[0].connector_id == "drive-sync"
    assert settings.google_drive.connectors[0].credential_ref == "file:///secure/google.json"
    assert settings.google_drive.connectors[0].tenant_id == "tenant-a"
    assert settings.google_drive.connectors[0].kb_id == "kb-a"
