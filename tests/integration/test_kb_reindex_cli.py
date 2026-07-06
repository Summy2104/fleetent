from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest
import yaml


def _write_yaml(path: Path, doc: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _service_doc() -> dict[str, object]:
    return {
        "service": {
            "tenant_id": "tenant-a",
            "service_key_ref": "env:FLEETENT_KB_SERVICE_KEY",
            "host": "127.0.0.1",
            "port": 8768,
        },
        "data": {
            "home": "./data",
        },
        "retrieval": {
            "default_mode": "hybrid",
            "top_k": 8,
        },
        "embedding": {
            "endpoint": "",
            "model": "",
            "dimensions": 384,
        },
        "extraction": {
            "enabled": False,
            "endpoint": "",
            "model": "",
        },
        "chunking": {
            "chunk_size": 900,
            "chunk_overlap": 150,
        },
        "connectors": [],
    }


def test_worker_reindex_job_rebuilds_kb_namespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import kb_ingest_jobs, vector_store
    from fleetent.knowledge_base import worker
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.worker import _knowledge_database

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    data_dir = tmp_path / "data"
    queue_url = f"sqlite:///{data_dir / 'kb_ingest_queue.db'}"
    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=_knowledge_database("tenant-a", data_dir=data_dir),
    )

    captured: dict[str, object] = {}

    def fake_reindex(request: vector_store.ReindexRequest) -> vector_store.ReindexSummary:
        captured["request"] = request
        return vector_store.ReindexSummary(
            owner=request.owner,
            namespace=vector_store.knowledge_namespace(request.tenant_id, request.kb_id or ""),
            dry_run=request.dry_run,
            scanned=0,
            reindexed=0,
            skipped=0,
            failed=0,
        )

    monkeypatch.setattr(vector_store, "reindex", fake_reindex)
    job = kb_ingest_jobs.enqueue_job(
        job_type="reindex",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={},
        database_url=queue_url,
    )
    claimed = kb_ingest_jobs.claim_next_job(database_url=queue_url)

    assert claimed is not None
    result = worker.run_job(claimed, data_dir=data_dir, queue_database_url=queue_url)

    assert result == {
        "namespace": "kb:tenant-a:kb-a",
        "owner": "knowledge_base",
        "dry_run": False,
        "scanned": 0,
        "reindexed": 0,
        "skipped": 0,
        "failed": 0,
    }
    assert captured["request"] == vector_store.ReindexRequest(
        owner="knowledge_base",
        tenant_id="tenant-a",
        kb_id="kb-a",
    )
    assert job["job_type"] == "reindex"


def test_kb_reindex_cli_enqueues_reindex_job(tmp_path: Path) -> None:
    from fleetent import kb_ingest_jobs
    from fleetent.knowledge_base import reindex_cli
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.worker import _knowledge_database

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    data_dir = tmp_path / "data"
    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=_knowledge_database("tenant-a", data_dir=data_dir),
    )

    reindex_cli.main(["--config", str(path), "--kb", "kb-a"])

    job = kb_ingest_jobs.claim_next_job(database_url=f"sqlite:///{data_dir / 'kb_ingest_queue.db'}")
    assert job is not None
    assert job["job_type"] == "reindex"
    assert job["tenant_id"] == "tenant-a"
    assert job["kb_id"] == "kb-a"


def test_kb_reindex_cli_rejects_missing_kb_without_enqueuing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from fleetent.knowledge_base import reindex_cli

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())

    with pytest.raises(SystemExit) as exc_info:
        reindex_cli.main(["--config", str(path), "--kb", "kb-missing"])

    assert exc_info.value.code == 1
    assert "fleetent kb create" in capsys.readouterr().err
    assert not (tmp_path / "data" / "kb_ingest_queue.db").exists()


def test_kb_reindex_cli_waits_for_terminal_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from fleetent import kb_ingest_jobs
    from fleetent.knowledge_base import reindex_cli
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.worker import _knowledge_database

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    data_dir = tmp_path / "data"
    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=_knowledge_database("tenant-a", data_dir=data_dir),
    )

    original_enqueue_job = kb_ingest_jobs.enqueue_job
    states: list[dict[str, object]] = []

    def fake_enqueue_job(**kwargs: object) -> dict[str, object]:
        job = original_enqueue_job(**kwargs)
        job_id = str(job["id"])
        states.extend(
            [
                {"id": job_id, "status": "pending"},
                {
                    "id": job_id,
                    "status": "done",
                    "connector_ref": (
                        '{"__request__":{},'
                        '"__result__":{"scanned":4,"reindexed":4,"skipped":0,"failed":0}}'
                    ),
                },
            ]
        )
        return job

    def fake_get_job(job_id: str, **kwargs: object) -> dict[str, object]:
        state = states.pop(0)
        assert state["id"] == job_id
        return state

    monkeypatch.setattr(reindex_cli.kb_ingest_jobs, "enqueue_job", fake_enqueue_job)
    monkeypatch.setattr(reindex_cli.kb_ingest_jobs, "get_job", fake_get_job)
    monkeypatch.setattr(reindex_cli.time, "sleep", lambda _: None)

    reindex_cli.main(["--config", str(path), "--kb", "kb-a", "--wait"])

    assert capsys.readouterr().out == "scanned=4 reindexed=4 skipped=0 failed=0\n"


def test_kb_reindex_cli_rebuilds_vectors_for_existing_chunks(tmp_path: Path) -> None:
    from fleetent import knowledge_base as kb_runtime
    from fleetent.knowledge_base import create_cli, ingest_cli, reindex_cli, worker
    from fleetent.knowledge_base.service_config import load_kb_service_config

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    guide_path = docs_dir / "guide.md"
    guide_path.write_text("# Guide\nRunbook recovery procedure", encoding="utf-8")

    config = load_kb_service_config(path)
    data_dir = config.data_dir()
    queue_url = config.queue_database_url()
    create_cli.main(["--config", str(path), "--kb", "kb-a", "--description", "Standalone KB"])
    ingest_cli.main(["--config", str(path), "--kb", "kb-a", str(guide_path)])
    ingest_result = worker.run_once(queue_database_url=queue_url, data_dir=data_dir)
    assert ingest_result is not None
    assert ingest_result["status"] == "done"

    def vector_search() -> list[object]:
        with worker._use_kb_runtime(
            "tenant-a",
            data_dir=data_dir,
            queue_database_url=queue_url,
        ):
            return asyncio.run(
                kb_runtime.search(
                    "Runbook recovery procedure",
                    tenant_id="tenant-a",
                    kb_ids=["kb-a"],
                    limit=1,
                    mode="vector",
                )
            )

    assert [chunk.filename for chunk in vector_search()] == ["guide.md"]

    for suffix in ("", "-wal", "-shm"):
        candidate = data_dir / f"kb_vectors.db{suffix}"
        if candidate.exists():
            candidate.unlink()

    assert vector_search() == []

    processed: list[dict[str, object] | None] = []

    def process_reindex_job() -> None:
        deadline = time.time() + 5.0
        while time.time() < deadline:
            result = worker.run_once(queue_database_url=queue_url, data_dir=data_dir)
            if result is not None:
                processed.append(result)
                return
            time.sleep(0.05)
        processed.append(None)

    worker_thread = threading.Thread(target=process_reindex_job, daemon=True)
    worker_thread.start()
    reindex_cli.main(["--config", str(path), "--kb", "kb-a", "--wait"])
    worker_thread.join(timeout=5.0)

    assert processed == [{"job_id": processed[0]["job_id"], "status": "done"}]
    assert [chunk.filename for chunk in vector_search()] == ["guide.md"]


def test_worker_reindex_job_updates_kb_embedding_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful reindex is the sanctioned embedding-model migration path — it
    must move the KB's recorded identity to the current runtime identity, or the
    retrieval mismatch guard stays locked forever after a model switch."""
    from fleetent import kb_ingest_jobs, vector_store
    from fleetent.knowledge_base import worker
    from fleetent.knowledge_base.core import KnowledgeStore
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.worker import _knowledge_database

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    data_dir = tmp_path / "data"
    queue_url = f"sqlite:///{data_dir / 'kb_ingest_queue.db'}"
    database = _knowledge_database("tenant-a", data_dir=data_dir)
    create_knowledge_base("tenant-a", "kb-a", "Standalone KB", database=database)
    store = KnowledgeStore(database)
    store.set_embedding_identity("tenant-a", "kb-a", "old-model", 111)

    def fake_reindex(request: vector_store.ReindexRequest) -> vector_store.ReindexSummary:
        return vector_store.ReindexSummary(
            owner=request.owner,
            namespace=vector_store.knowledge_namespace(request.tenant_id, request.kb_id or ""),
            dry_run=request.dry_run,
            scanned=3,
            reindexed=3,
            skipped=0,
            failed=0,
        )

    monkeypatch.setattr(vector_store, "reindex", fake_reindex)
    kb_ingest_jobs.enqueue_job(
        job_type="reindex",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={},
        database_url=queue_url,
    )
    claimed = kb_ingest_jobs.claim_next_job(database_url=queue_url)
    assert claimed is not None

    worker.run_job(claimed, data_dir=data_dir, queue_database_url=queue_url)

    current = vector_store.current_embedding_identity()
    assert store.get_embedding_identity("tenant-a", "kb-a") == (
        current.model,
        current.dimensions,
    )


def test_worker_reindex_job_keeps_identity_when_rebuild_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import kb_ingest_jobs, vector_store
    from fleetent.knowledge_base import worker
    from fleetent.knowledge_base.core import KnowledgeStore
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.worker import _knowledge_database

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    data_dir = tmp_path / "data"
    queue_url = f"sqlite:///{data_dir / 'kb_ingest_queue.db'}"
    database = _knowledge_database("tenant-a", data_dir=data_dir)
    create_knowledge_base("tenant-a", "kb-a", "Standalone KB", database=database)
    store = KnowledgeStore(database)
    store.set_embedding_identity("tenant-a", "kb-a", "old-model", 111)

    def fake_reindex(request: vector_store.ReindexRequest) -> vector_store.ReindexSummary:
        return vector_store.ReindexSummary(
            owner=request.owner,
            namespace=vector_store.knowledge_namespace(request.tenant_id, request.kb_id or ""),
            dry_run=request.dry_run,
            scanned=3,
            reindexed=1,
            skipped=0,
            failed=2,
        )

    monkeypatch.setattr(vector_store, "reindex", fake_reindex)
    kb_ingest_jobs.enqueue_job(
        job_type="reindex",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={},
        database_url=queue_url,
    )
    claimed = kb_ingest_jobs.claim_next_job(database_url=queue_url)
    assert claimed is not None

    worker.run_job(claimed, data_dir=data_dir, queue_database_url=queue_url)

    assert store.get_embedding_identity("tenant-a", "kb-a") == ("old-model", 111)
