from __future__ import annotations

import os
from pathlib import Path

from fleetent import kb_ingest_jobs
from fleetent.knowledge_base.core import KnowledgeStore
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.knowledge_base.management.runtime import create_knowledge_base
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter


def _tenant_db(home_dir: Path, tenant_id: str):
    scope = TenantRouter(SQLiteTenantBackend(data_dir=home_dir)).tenant_scope(tenant_id)
    return scope.open_kb_db(KB_MIGRATIONS)


def _tenant_queue_url(home_dir: Path, tenant_id: str) -> str:
    return f"sqlite:///{home_dir / 'tenants' / tenant_id / 'kb' / 'data' / 'kb_ingest_queue.db'}"


def _seed_kb(home_dir: Path, tenant_id: str, kb_id: str) -> None:
    create_knowledge_base(tenant_id, kb_id, f"{tenant_id} KB", database=_tenant_db(home_dir, tenant_id))


def test_worker_run_once_discovers_and_drains_multiple_tenant_queues(
    tmp_path: Path,
) -> None:
    from fleetent.knowledge_base import worker

    _seed_kb(tmp_path, "tenant-a", "kb-a")
    _seed_kb(tmp_path, "tenant-b", "kb-b")
    kb_ingest_jobs.enqueue_job(
        job_type="import_document",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={
            "source": "a.md",
            "content": "# Alpha\nTenant A handbook",
            "document_format": "markdown",
        },
        database_url=_tenant_queue_url(tmp_path, "tenant-a"),
    )
    kb_ingest_jobs.enqueue_job(
        job_type="import_document",
        tenant_id="tenant-b",
        kb_id="kb-b",
        connector_ref={
            "source": "b.md",
            "content": "# Beta\nTenant B playbook",
            "document_format": "markdown",
        },
        database_url=_tenant_queue_url(tmp_path, "tenant-b"),
    )

    first = worker.run_once(home_dir=tmp_path)
    second = worker.run_once(home_dir=tmp_path)

    assert first == {"job_id": first["job_id"], "status": "done"}
    assert second == {"job_id": second["job_id"], "status": "done"}
    assert KnowledgeStore(_tenant_db(tmp_path, "tenant-a")).list_documents("tenant-a", "kb-a")[0][
        "filename"
    ] == "a.md"
    assert KnowledgeStore(_tenant_db(tmp_path, "tenant-b")).list_documents("tenant-b", "kb-b")[0][
        "filename"
    ] == "b.md"

    _seed_kb(tmp_path, "tenant-c", "kb-c")
    kb_ingest_jobs.enqueue_job(
        job_type="import_document",
        tenant_id="tenant-c",
        kb_id="kb-c",
        connector_ref={
            "source": "c.md",
            "content": "# Gamma\nTenant C notes",
            "document_format": "markdown",
        },
        database_url=_tenant_queue_url(tmp_path, "tenant-c"),
    )

    third = worker.run_once(home_dir=tmp_path)

    assert third == {"job_id": third["job_id"], "status": "done"}
    assert KnowledgeStore(_tenant_db(tmp_path, "tenant-c")).list_documents("tenant-c", "kb-c")[0][
        "filename"
    ] == "c.md"


def test_worker_connector_sync_uses_job_tenant_env_and_tenant_lock(
    tmp_path: Path, monkeypatch
) -> None:
    from fleetent.knowledge_base import worker

    for tenant_id, secret in (("tenant-a", "secret-a"), ("tenant-b", "secret-b")):
        tenant_dir = tmp_path / "tenants" / tenant_id / "kb"
        tenant_dir.mkdir(parents=True, exist_ok=True)
        tenant_dir.joinpath("connectors.yaml").write_text(
            """
connectors:
  - id: drive-sync
    type: google_drive
    enabled: true
    kb_id: kb-sync
    access_token_env: SHARED_SYNC_TOKEN
""".strip()
            + "\n",
            encoding="utf-8",
        )
        tenant_dir.joinpath(".env").write_text(
            f"SHARED_SYNC_TOKEN={secret}\n",
            encoding="utf-8",
        )
        _seed_kb(tmp_path, tenant_id, "kb-sync")
    monkeypatch.delenv("SHARED_SYNC_TOKEN", raising=False)

    queue_a = _tenant_queue_url(tmp_path, "tenant-a")
    queue_b = _tenant_queue_url(tmp_path, "tenant-b")
    job_a = kb_ingest_jobs.enqueue_job(
        job_type="connector_sync",
        tenant_id="tenant-a",
        kb_id="kb-sync",
        connector_ref={
            "connector_id": "drive-sync",
            "kind": "google_drive",
            "config": {"access_token_env": "SHARED_SYNC_TOKEN"},
        },
        database_url=queue_a,
    )
    job_b = kb_ingest_jobs.enqueue_job(
        job_type="connector_sync",
        tenant_id="tenant-b",
        kb_id="kb-sync",
        connector_ref={
            "connector_id": "drive-sync",
            "kind": "google_drive",
            "config": {"access_token_env": "SHARED_SYNC_TOKEN"},
        },
        database_url=queue_b,
    )

    seen_tokens: list[str] = []

    async def fake_run_connector_sync(*args, **kwargs):
        seen_tokens.append(os.environ["SHARED_SYNC_TOKEN"])

        class Result:
            connector_id = "drive-sync"
            status = "done"
            summary = "ok"
            error = ""

        return Result()

    monkeypatch.setattr(worker.knowledge_base, "run_connector_sync", fake_run_connector_sync)

    result = worker.run_once(home_dir=tmp_path, tenant_id="tenant-a")

    assert result == {"job_id": job_a["id"], "status": "done"}
    assert seen_tokens == ["secret-a"]
    assert kb_ingest_jobs.get_job(job_b["id"], database_url=queue_b)["status"] == "pending"
