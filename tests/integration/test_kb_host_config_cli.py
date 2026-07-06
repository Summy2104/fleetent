from __future__ import annotations

import json
from pathlib import Path

import yaml

from fleetent import kb_ingest_jobs
from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
from fleetent.knowledge_base.management.runtime import create_knowledge_base
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter


def _write_yaml(path: Path, doc: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _host_service_doc() -> dict[str, object]:
    return {
        "service": {
            "service_key_ref": "env:FLEETENT_KB_SERVICE_KEY",
            "host": "127.0.0.1",
            "port": 8768,
        },
        "retrieval": {"default_mode": "hybrid", "top_k": 8},
        "embedding": {"endpoint": "", "model": "", "dimensions": 384},
        "extraction": {"enabled": False, "endpoint": "", "model": ""},
        "chunking": {"chunk_size": 900, "chunk_overlap": 150},
    }


def _tenant_db(home_dir: Path, tenant_id: str):
    scope = TenantRouter(SQLiteTenantBackend(data_dir=home_dir)).tenant_scope(tenant_id)
    return scope.open_kb_db(KB_MIGRATIONS)


def _tenant_queue_url(home_dir: Path, tenant_id: str) -> str:
    return f"sqlite:///{home_dir / 'tenants' / tenant_id / 'kb' / 'data' / 'kb_ingest_queue.db'}"


def test_kb_create_cli_supports_host_config_with_explicit_tenant(tmp_path: Path) -> None:
    from fleetent.knowledge_base import create_cli

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _host_service_doc())

    create_cli.main(
        ["--config", str(path), "--tenant", "tenant-a", "--kb", "kb-a", "--description", "Host KB"]
    )

    rows = (
        _tenant_db(tmp_path, "tenant-a")
        .execute(
            """
        SELECT tenant_id, kb_id, description
        FROM knowledge_bases
        ORDER BY kb_id ASC
        """
        )
        .fetchall()
    )
    assert rows == [{"tenant_id": "tenant-a", "kb_id": "kb-a", "description": "Host KB"}]


def test_kb_ingest_cli_supports_host_config_end_to_end(tmp_path: Path, monkeypatch) -> None:
    from fleetent import vector_store
    from fleetent.knowledge_base import create_cli, ingest_cli, worker

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _host_service_doc())
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("# Guide\nRunbook", encoding="utf-8")

    async def embed_text(text: str) -> list[float]:
        return [float(len(text)), 0.0]

    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    create_cli.main(["--config", str(path), "--tenant", "tenant-a", "--kb", "kb-a"])

    ingest_cli.main(["--config", str(path), "--tenant", "tenant-a", "--kb", "kb-a", str(docs_dir)])
    result = worker.run_once(home_dir=tmp_path, tenant_id="tenant-a")

    assert result is not None
    assert result["status"] == "done"
    rows = (
        _tenant_db(tmp_path, "tenant-a")
        .execute("SELECT filename FROM knowledge_documents ORDER BY created_at ASC")
        .fetchall()
    )
    assert rows == [{"filename": "guide.md"}]


def test_host_config_extract_and_reindex_cli_enqueue_to_selected_tenant_queue(
    tmp_path: Path,
) -> None:
    from fleetent.knowledge_base import create_cli, extract_cli, reindex_cli

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _host_service_doc())
    create_cli.main(["--config", str(path), "--tenant", "tenant-a", "--kb", "kb-a"])
    create_knowledge_base("tenant-a", "kb-a", database=_tenant_db(tmp_path, "tenant-a"))

    _tenant_db(tmp_path, "tenant-a").execute(
        """
        INSERT INTO knowledge_documents (id, tenant_id, kb_id, filename, source, source_url, created_at)
        VALUES ('doc-1', 'tenant-a', 'kb-a', 'guide.md', 'guide.md', NULL, '2026-07-02T00:00:00+00:00')
        """
    )

    extract_cli.main(["--config", str(path), "--tenant", "tenant-a", "--kb", "kb-a"])
    reindex_cli.main(["--config", str(path), "--tenant", "tenant-a", "--kb", "kb-a"])

    queue_url = _tenant_queue_url(tmp_path, "tenant-a")
    first = kb_ingest_jobs.claim_next_job(database_url=queue_url)
    second = kb_ingest_jobs.claim_next_job(database_url=queue_url)

    assert {first["job_type"], second["job_type"]} == {"extraction", "reindex"}
    extraction = first if first["job_type"] == "extraction" else second
    assert json.loads(str(extraction["connector_ref"])) == {"document_id": "doc-1"}
