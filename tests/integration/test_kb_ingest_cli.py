from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient


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


def test_kb_ingest_cli_enqueues_sync_directory_job(tmp_path: Path) -> None:
    from fleetent import kb_ingest_jobs
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.worker import _knowledge_database

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide", encoding="utf-8")

    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=_knowledge_database(
            "tenant-a", data_dir=tmp_path / "data", migrations=KB_MIGRATIONS
        ),
    )

    from fleetent.knowledge_base import ingest_cli

    ingest_cli.main(["--config", str(path), "--kb", "kb-a", str(docs_dir)])

    job = kb_ingest_jobs.claim_next_job(
        database_url=f"sqlite:///{tmp_path / 'data' / 'kb_ingest_queue.db'}"
    )
    assert job is not None
    assert job["job_type"] == "sync_directory"
    assert job["tenant_id"] == "tenant-a"
    assert job["kb_id"] == "kb-a"
    assert json.loads(str(job["connector_ref"])) == {"path": str(docs_dir.resolve())}


def test_kb_ingest_cli_directory_runs_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import vector_store
    from fleetent.knowledge_base import ingest_cli, worker
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.worker import _knowledge_database

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide\nRunbook", encoding="utf-8")
    (docs_dir / "notes.txt").write_text("plain text", encoding="utf-8")

    async def embed_text(text: str) -> list[float]:
        return [float(len(text)), 0.0]

    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=_knowledge_database(
            "tenant-a", data_dir=tmp_path / "data", migrations=KB_MIGRATIONS
        ),
    )

    ingest_cli.main(["--config", str(path), "--kb", "kb-a", str(docs_dir)])

    result = worker.run_once(
        queue_database_url=f"sqlite:///{tmp_path / 'data' / 'kb_ingest_queue.db'}",
        data_dir=tmp_path / "data",
    )

    assert result is not None
    assert result["status"] == "done"
    job = worker.kb_ingest_jobs.get_job(
        result["job_id"], database_url=f"sqlite:///{tmp_path / 'data' / 'kb_ingest_queue.db'}"
    )
    assert job is not None
    assert job["last_error"] is None
    kb_db = _knowledge_database("tenant-a", data_dir=tmp_path / "data", migrations=KB_MIGRATIONS)
    document_count = kb_db.execute("SELECT COUNT(*) AS count FROM knowledge_documents").fetchone()
    chunk_count = kb_db.execute("SELECT COUNT(*) AS count FROM knowledge_chunks").fetchone()
    assert document_count == {"count": 2}
    assert chunk_count is not None
    assert chunk_count["count"] >= 2


def test_kb_ingest_cli_single_file_runs_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import vector_store
    from fleetent.knowledge_base import ingest_cli, worker
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.worker import _knowledge_database

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    guide_path = docs_dir / "guide.md"
    guide_path.write_text("# Guide\nRunbook", encoding="utf-8")

    async def embed_text(text: str) -> list[float]:
        return [float(len(text)), 0.0]

    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=_knowledge_database(
            "tenant-a", data_dir=tmp_path / "data", migrations=KB_MIGRATIONS
        ),
    )

    ingest_cli.main(["--config", str(path), "--kb", "kb-a", str(guide_path)])

    result = worker.run_once(
        queue_database_url=f"sqlite:///{tmp_path / 'data' / 'kb_ingest_queue.db'}",
        data_dir=tmp_path / "data",
    )

    assert result is not None
    assert result["status"] == "done"
    kb_db = _knowledge_database("tenant-a", data_dir=tmp_path / "data", migrations=KB_MIGRATIONS)
    rows = kb_db.execute(
        "SELECT filename FROM knowledge_documents ORDER BY created_at ASC"
    ).fetchall()
    assert rows == [{"filename": "guide.md"}]


def test_kb_ingest_cli_directory_partial_failure_marks_done_with_last_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import vector_store
    from fleetent.knowledge_base import ingest_cli, worker
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.worker import _knowledge_database

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "good.md").write_text("# Good\nhealthy", encoding="utf-8")
    bad_path = docs_dir / "bad.md"
    bad_path.write_text("# Bad\ntoken: partial-secret", encoding="utf-8")

    async def embed_text(text: str) -> list[float]:
        if "partial-secret" in text:
            raise RuntimeError("token: partial-secret")
        return [float(len(text)), 0.0]

    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=_knowledge_database(
            "tenant-a", data_dir=tmp_path / "data", migrations=KB_MIGRATIONS
        ),
    )

    ingest_cli.main(["--config", str(path), "--kb", "kb-a", str(docs_dir)])

    result = worker.run_once(
        queue_database_url=f"sqlite:///{tmp_path / 'data' / 'kb_ingest_queue.db'}",
        data_dir=tmp_path / "data",
    )

    assert result is not None
    assert result["status"] == "done"
    job = worker.kb_ingest_jobs.get_job(
        result["job_id"], database_url=f"sqlite:///{tmp_path / 'data' / 'kb_ingest_queue.db'}"
    )
    assert job is not None
    assert job["status"] == "done"
    assert str(job["last_error"]).startswith(str(bad_path.resolve()))
    assert "partial-secret" not in str(job["last_error"])
    assert "[REDACTED]" in str(job["last_error"])


def test_kb_ingest_cli_directory_embedding_failure_marks_failed_and_status_surfaces_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import vector_store
    from fleetent.knowledge_base import ingest_cli, serve, worker
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.worker import _knowledge_database

    monkeypatch.setenv("FLEETENT_KB_SERVICE_KEY", "svc-test")

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    bad_path = docs_dir / "bad.md"
    bad_path.write_text("# Bad\ntoken: total-secret", encoding="utf-8")

    async def embed_text(text: str) -> list[float]:
        raise RuntimeError(f"token: total-secret for {text}")

    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=_knowledge_database(
            "tenant-a", data_dir=tmp_path / "data", migrations=KB_MIGRATIONS
        ),
    )

    ingest_cli.main(["--config", str(path), "--kb", "kb-a", str(docs_dir)])

    first = worker.run_once(
        queue_database_url=f"sqlite:///{tmp_path / 'data' / 'kb_ingest_queue.db'}",
        data_dir=tmp_path / "data",
    )
    second = worker.run_once(
        queue_database_url=f"sqlite:///{tmp_path / 'data' / 'kb_ingest_queue.db'}",
        data_dir=tmp_path / "data",
    )
    result = worker.run_once(
        queue_database_url=f"sqlite:///{tmp_path / 'data' / 'kb_ingest_queue.db'}",
        data_dir=tmp_path / "data",
    )

    assert first is not None
    assert second is not None
    assert result is not None
    assert first["status"] == "pending"
    assert second["status"] == "pending"
    assert result["status"] == "failed"
    job = worker.kb_ingest_jobs.get_job(
        result["job_id"], database_url=f"sqlite:///{tmp_path / 'data' / 'kb_ingest_queue.db'}"
    )
    assert job is not None
    assert job["status"] == "failed"
    assert str(job["last_error"]).startswith(str(bad_path.resolve()))
    assert "total-secret" not in str(job["last_error"])
    assert "[REDACTED]" in str(job["last_error"])

    kb_db = _knowledge_database("tenant-a", data_dir=tmp_path / "data", migrations=KB_MIGRATIONS)
    rows = kb_db.execute(
        "SELECT filename FROM knowledge_documents ORDER BY created_at ASC"
    ).fetchall()
    assert rows == []

    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id="tenant-a",
            service_key_ref="env:FLEETENT_KB_SERVICE_KEY",
            data_dir=tmp_path / "data",
            queue_database_url=f"sqlite:///{tmp_path / 'data' / 'kb_ingest_queue.db'}",
        )
    )
    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.get(
            "/status",
            headers={
                "Authorization": "Bearer svc-test",
                "X-Fleetent-Principal": '{"user_id":"user-1","tenant_id":"tenant-a"}',
            },
        )

    assert response.status_code == 200
    status_jobs = response.json()["jobs"]
    assert len(status_jobs) == 1
    assert status_jobs[0]["status"] == "failed"
    assert status_jobs[0]["last_error"] == job["last_error"]


def test_kb_ingest_cli_rejects_missing_kb_without_enqueuing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from fleetent.knowledge_base import ingest_cli

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        ingest_cli.main(["--config", str(path), "--kb", "kb-missing", str(docs_dir)])

    assert exc_info.value.code == 1
    assert "POST /admin/kb" in capsys.readouterr().err

    assert not (tmp_path / "data" / "kb_ingest_queue.db").exists()
