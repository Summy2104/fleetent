import json

import pytest


@pytest.fixture
def queue_module():
    import fleetent.kb_ingest_jobs as queue

    return queue


@pytest.fixture
def queue_database_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'kb-queue.db'}"


def test_enqueue_claim_done_and_failed_retry(queue_module, queue_database_url):
    first = queue_module.enqueue_job(
        job_type="sync_directory",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={"path": "/srv/docs"},
        database_url=queue_database_url,
    )
    second = queue_module.enqueue_job(
        job_type="import_document",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={"source": "runbook.md", "document_format": "markdown", "content": "# H1"},
        max_attempts=2,
        database_url=queue_database_url,
    )

    assert first["status"] == "pending"
    assert first["attempts"] == 0
    assert first["cred_ref"] == ""

    claimed_first = queue_module.claim_next_job(database_url=queue_database_url)
    claimed_second = queue_module.claim_next_job(database_url=queue_database_url)
    assert claimed_first is not None
    assert claimed_second is not None
    assert {claimed_first["id"], claimed_second["id"]} == {first["id"], second["id"]}
    assert claimed_first["id"] != claimed_second["id"]
    assert queue_module.claim_next_job(database_url=queue_database_url) is None

    done = queue_module.mark_done(claimed_first["id"], database_url=queue_database_url)
    assert done is not None
    assert done["status"] == "done"
    assert done["finished_at"] is not None

    requeued = queue_module.mark_failed(
        claimed_second["id"], "temporary failure", database_url=queue_database_url
    )
    assert requeued is not None
    assert requeued["status"] == "pending"
    assert requeued["attempts"] == 1
    assert requeued["finished_at"] is None

    retried = queue_module.claim_next_job(database_url=queue_database_url)
    assert retried is not None
    assert retried["id"] == claimed_second["id"]

    failed = queue_module.mark_failed(
        retried["id"], "terminal failure", database_url=queue_database_url
    )
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["attempts"] == 2
    assert failed["finished_at"] is not None
    assert failed["last_error"] == "terminal failure"


def test_enqueue_connector_job_uses_refs_not_plaintext(queue_module, queue_database_url):
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

    job = queue_module.enqueue_connector_job(connector_row, database_url=queue_database_url)

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


def test_list_jobs_filters_by_tenant_and_kb_and_decodes_result(queue_module, queue_database_url):
    target = queue_module.enqueue_job(
        job_type="import_document",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={"source": "runbook.md", "document_format": "markdown", "content": "# H1"},
        database_url=queue_database_url,
    )
    other_kb = queue_module.enqueue_job(
        job_type="import_document",
        tenant_id="tenant-a",
        kb_id="kb-b",
        connector_ref={"source": "other.md", "document_format": "markdown", "content": "# H2"},
        database_url=queue_database_url,
    )
    other_tenant = queue_module.enqueue_job(
        job_type="sync_directory",
        tenant_id="tenant-b",
        kb_id="kb-a",
        connector_ref={"path": "/srv/docs"},
        database_url=queue_database_url,
    )

    done = queue_module.mark_done(
        target["id"],
        result={"document_id": "doc-1", "chunks": 4},
        database_url=queue_database_url,
    )
    assert done is not None
    failed = queue_module.mark_failed(other_kb["id"], "boom", database_url=queue_database_url)
    assert failed is not None
    assert other_tenant["id"]

    jobs = queue_module.list_jobs(tenant_id="tenant-a", kb_id="kb-a", database_url=queue_database_url)

    assert jobs == [
        {
            "id": target["id"],
            "job_type": "import_document",
            "tenant_id": "tenant-a",
            "kb_id": "kb-a",
            "connector_ref": done["connector_ref"],
            "cred_ref": "",
            "status": "done",
            "attempts": 0,
            "max_attempts": 3,
            "last_error": None,
            "created_at": done["created_at"],
            "updated_at": done["updated_at"],
            "claimed_at": None,
            "finished_at": done["finished_at"],
            "result": {"document_id": "doc-1", "chunks": 4},
        }
    ]
