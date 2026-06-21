import json

import pytest

from tests.integration._migration_template import apply_migrations


@pytest.fixture
def queue_module(tmp_path, monkeypatch):
    db_path = tmp_path / "management.db"
    apply_migrations(db_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    import fleetent.kb_ingest_jobs as queue

    return queue


def test_enqueue_claim_done_and_failed_retry(queue_module):
    first = queue_module.enqueue_job(
        job_type="sync_directory",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={"path": "/srv/docs"},
    )
    second = queue_module.enqueue_job(
        job_type="import_document",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={"source": "runbook.md", "document_format": "markdown", "content": "# H1"},
        max_attempts=2,
    )

    assert first["status"] == "pending"
    assert first["attempts"] == 0
    assert first["cred_ref"] == ""

    claimed_first = queue_module.claim_next_job()
    claimed_second = queue_module.claim_next_job()
    assert claimed_first is not None
    assert claimed_second is not None
    assert {claimed_first["id"], claimed_second["id"]} == {first["id"], second["id"]}
    assert claimed_first["id"] != claimed_second["id"]
    assert queue_module.claim_next_job() is None

    done = queue_module.mark_done(claimed_first["id"])
    assert done is not None
    assert done["status"] == "done"
    assert done["finished_at"] is not None

    requeued = queue_module.mark_failed(claimed_second["id"], "temporary failure")
    assert requeued is not None
    assert requeued["status"] == "pending"
    assert requeued["attempts"] == 1
    assert requeued["finished_at"] is None

    retried = queue_module.claim_next_job()
    assert retried is not None
    assert retried["id"] == claimed_second["id"]

    failed = queue_module.mark_failed(retried["id"], "terminal failure")
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["attempts"] == 2
    assert failed["finished_at"] is not None
    assert failed["last_error"] == "terminal failure"


def test_enqueue_connector_job_uses_refs_not_plaintext(queue_module):
    connector_row = {
        "connector_id": "drive-sync",
        "kind": "google_drive",
        "tenant_id": "tenant-a",
        "kb_id": "kb-a",
        "config": {
            "folder_id": "folder-123",
            "credential_ref": "file:///secure/google.json",
            "client_id_env": "GDRIVE_CLIENT_ID",
            "client_secret_env": "GDRIVE_CLIENT_SECRET",
        },
    }

    job = queue_module.enqueue_connector_job(connector_row)

    assert job["job_type"] == "connector_sync"
    assert job["cred_ref"] == "file:///secure/google.json"
    payload = json.loads(job["connector_ref"])
    assert payload == {
        "connector_id": "drive-sync",
        "kind": "google_drive",
        "config": {
            "folder_id": "folder-123",
            "client_id_env": "GDRIVE_CLIENT_ID",
            "client_secret_env": "GDRIVE_CLIENT_SECRET",
        },
    }
    assert "credential_ref" not in payload["config"]
    assert "google.json" not in job["connector_ref"]
