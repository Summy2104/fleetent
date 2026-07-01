from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
import yaml
from fastapi.testclient import TestClient


def _write_yaml(path, doc: dict[str, object]) -> None:
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
            "endpoint": "http://127.0.0.1:11434/v1/embeddings",
            "model": "bge-small",
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
        "connectors": [
            {
                "id": "drive-a",
                "type": "google_drive",
                "enabled": True,
                "kb_id": "kb-a",
                "folder_id": "folder-1",
                "recursive": True,
                "credential_ref": "env:KB_SHARED_GOOGLE_DRIVE",
                "sync_interval_seconds": 1800,
            },
            {
                "id": "confluence-a",
                "type": "confluence",
                "enabled": True,
                "kb_id": "kb-a",
                "base_url": "https://example.atlassian.net/wiki",
                "space_key": "ENG",
                "username_env": "KB_CONFLUENCE_USERNAME",
                "credential_ref": "file:///secure/confluence.token",
            },
        ],
    }


def test_load_kb_service_config_builds_operations_snapshot(tmp_path) -> None:
    from fleetent.knowledge_base import list_configured_connectors
    from fleetent.knowledge_base.service_config import load_kb_service_config

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())

    config = load_kb_service_config(path)
    connectors = list_configured_connectors(settings=config.connector_settings())

    assert config.service.tenant_id == "tenant-a"
    assert config.chunking.chunk_size == 900
    assert [(item.connector_id, item.connector_type, item.kb_id) for item in connectors] == [
        ("drive-a", "google_drive", "kb-a"),
        ("confluence-a", "confluence", "kb-a"),
    ]


def test_validate_kb_service_boot_requires_embedding_and_connector_secrets(
    tmp_path, monkeypatch
) -> None:
    from fleetent.knowledge_base.service_config import (
        load_kb_service_config,
        validate_kb_service_boot,
    )

    path = tmp_path / "kb-service.yaml"
    doc = _service_doc()
    doc["embedding"] = {"endpoint": "", "model": "bge-small", "dimensions": 384}  # type: ignore[index]
    _write_yaml(path, doc)

    config = load_kb_service_config(path)
    with pytest.raises(ValueError, match="embedding endpoint"):
        validate_kb_service_boot(config)

    doc["embedding"] = {  # type: ignore[index]
        "endpoint": "http://127.0.0.1:11434/v1/embeddings",
        "model": "bge-small",
        "dimensions": 384,
    }
    doc["connectors"][1]["credential_ref"] = "env:KB_CONFLUENCE_TOKEN"  # type: ignore[index]
    _write_yaml(path, doc)
    config = load_kb_service_config(path)

    monkeypatch.delenv("KB_SHARED_GOOGLE_DRIVE", raising=False)
    monkeypatch.delenv("KB_CONFLUENCE_TOKEN", raising=False)
    with pytest.raises(ValueError, match="KB_SHARED_GOOGLE_DRIVE"):
        validate_kb_service_boot(config)

    monkeypatch.setenv("KB_SHARED_GOOGLE_DRIVE", '{"client_email":"svc@example.com"}')
    with pytest.raises(ValueError, match="KB_CONFLUENCE_TOKEN"):
        validate_kb_service_boot(config)

    monkeypatch.setenv("KB_CONFLUENCE_TOKEN", "token-value")
    validate_kb_service_boot(config)


def test_validate_kb_service_boot_requires_embedding_and_extraction_api_keys(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.knowledge_base.service_config import (
        load_kb_service_config,
        validate_kb_service_boot,
    )

    path = tmp_path / "kb-service.yaml"
    doc = _service_doc()
    doc["connectors"] = []  # type: ignore[index]
    doc["embedding"]["api_key_env"] = "FLEETENT_KB_EMBEDDING_API_KEY"  # type: ignore[index]
    doc["extraction"] = {  # type: ignore[index]
        "enabled": True,
        "endpoint": "http://llm.example/v1",
        "model": "kb-extract",
        "api_key_env": "FLEETENT_KB_EXTRACTION_API_KEY",
    }
    _write_yaml(path, doc)

    config = load_kb_service_config(path)

    monkeypatch.delenv("FLEETENT_KB_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("FLEETENT_KB_EXTRACTION_API_KEY", raising=False)
    with pytest.raises(ValueError, match="FLEETENT_KB_EMBEDDING_API_KEY"):
        validate_kb_service_boot(config)

    monkeypatch.setenv("FLEETENT_KB_EMBEDDING_API_KEY", "embed-secret")
    with pytest.raises(ValueError, match="FLEETENT_KB_EXTRACTION_API_KEY"):
        validate_kb_service_boot(config)

    monkeypatch.setenv("FLEETENT_KB_EXTRACTION_API_KEY", "extract-secret")
    validate_kb_service_boot(config)


def test_standalone_worker_resolves_shared_env_credentials_locally(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import kb_ingest_jobs
    from fleetent.knowledge_base import worker
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.service_config import load_kb_service_config

    path = tmp_path / "kb-service.yaml"
    doc = _service_doc()
    doc["connectors"] = [  # type: ignore[index]
        {
            "id": "conf-a",
            "type": "confluence",
            "enabled": True,
            "kb_id": "kb-a",
            "base_url": "https://example.atlassian.net/wiki",
            "space_key": "ENG",
            "username": "bot@example.com",
            "credential_ref": "env:KB_SHARED_TOKEN",
        },
        {
            "id": "conf-b",
            "type": "confluence",
            "enabled": True,
            "kb_id": "kb-a",
            "base_url": "https://example.atlassian.net/wiki",
            "space_key": "OPS",
            "username": "bot@example.com",
            "credential_ref": "env:KB_SHARED_TOKEN",
        },
    ]
    _write_yaml(path, doc)
    config = load_kb_service_config(path)
    queue_url = config.queue_database_url()
    data_dir = config.data_dir()

    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=worker._knowledge_database(
            "tenant-a", data_dir=data_dir, migrations=KB_MIGRATIONS
        ),
    )

    monkeypatch.setenv("KB_SHARED_TOKEN", "shared-secret")
    seen_payloads: list[str] = []

    async def fake_sync_confluence(connector_config, *, client):
        from fleetent.knowledge_base.connectors.confluence import (
            ConfluenceSyncSummary,
            CredentialRefResolver,
        )

        seen_payloads.append(
            CredentialRefResolver().resolve(connector_config.credential_ref).payload
        )
        return ConfluenceSyncSummary(scanned=1, planned=1, ingested=0)

    monkeypatch.setattr(worker.knowledge_base, "sync_confluence", fake_sync_confluence)
    for row in config.connector_rows():
        kb_ingest_jobs.enqueue_connector_job(row, database_url=queue_url)

    first = worker.run_once(queue_database_url=queue_url, data_dir=data_dir)
    second = worker.run_once(queue_database_url=queue_url, data_dir=data_dir)

    assert first is not None
    assert second is not None
    assert seen_payloads == ["shared-secret", "shared-secret"]


def test_standalone_queue_and_worker_use_local_sqlite_not_management_db(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import kb_ingest_jobs, vector_store
    from fleetent.knowledge_base import worker
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.service_config import load_kb_service_config

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    config = load_kb_service_config(path)
    queue_url = config.queue_database_url()
    data_dir = config.data_dir()

    async def embed_text(text: str) -> list[float]:
        return [float(len(text)), 0.0]

    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=worker._knowledge_database(
            "tenant-a", data_dir=data_dir, migrations=KB_MIGRATIONS
        ),
    )

    job = kb_ingest_jobs.enqueue_job(
        job_type="import_document",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={
            "source": "guide.md",
            "content": "# Intro\nRunbook",
            "document_format": "markdown",
        },
        database_url=queue_url,
    )

    result = worker.run_once(queue_database_url=queue_url, data_dir=data_dir)

    assert result == {"job_id": job["id"], "status": "done"}
    assert not (tmp_path / "management.db").exists()
    local_job = kb_ingest_jobs.get_job(job["id"], database_url=queue_url)
    assert local_job is not None
    assert local_job["status"] == "done"
    kb_db = worker._knowledge_database(
        "tenant-a",
        data_dir=data_dir,
        migrations=KB_MIGRATIONS,
    )
    rows = kb_db.execute(
        "SELECT filename FROM knowledge_documents ORDER BY created_at ASC"
    ).fetchall()
    assert rows == [{"filename": "guide.md"}]


def test_standalone_import_triggers_local_extraction_and_writes_graph(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import kb_ingest_jobs, vector_store
    from fleetent.knowledge_base import extraction, worker
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.service_config import load_kb_service_config

    path = tmp_path / "kb-service.yaml"
    doc = _service_doc()
    doc["extraction"] = {"enabled": True, "endpoint": "inline://test", "model": "deterministic"}
    _write_yaml(path, doc)
    config = load_kb_service_config(path)
    queue_url = config.queue_database_url()
    data_dir = config.data_dir()

    async def embed_text(text: str) -> list[float]:
        return [float(len(text)), 0.0]

    async def fake_run_entity_extraction(
        tenant_id: str,
        kb_id: str,
        document_id: str | None = None,
        extractor: str = "deterministic",
    ):
        assert extractor == "model_policy"
        return await extraction.run_entity_extraction(
            tenant_id,
            kb_id,
            document_id=document_id,
            extractor="deterministic",
        )

    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    monkeypatch.setattr(worker.kb_runtime, "run_entity_extraction", fake_run_entity_extraction)
    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=worker._knowledge_database(
            "tenant-a", data_dir=data_dir, migrations=KB_MIGRATIONS
        ),
    )
    kb_db = worker._knowledge_database("tenant-a", data_dir=data_dir, migrations=KB_MIGRATIONS)
    kb_db.execute(
        """
        UPDATE knowledge_bases
        SET extraction_enabled = 1
        WHERE tenant_id = :tenant_id AND kb_id = :kb_id
        """,
        {"tenant_id": "tenant-a", "kb_id": "kb-a"},
    )

    job = kb_ingest_jobs.enqueue_job(
        job_type="import_document",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={
            "source": "graph.md",
            "content": "Customer: Acme\nDepends on: Billing API -> Data Warehouse",
            "document_format": "markdown",
        },
        database_url=queue_url,
    )

    ingest_result = worker.run_once(queue_database_url=queue_url, data_dir=data_dir)
    extraction_result = worker.run_once(queue_database_url=queue_url, data_dir=data_dir)

    assert ingest_result == {"job_id": job["id"], "status": "done"}
    assert extraction_result is not None
    assert extraction_result["status"] == "done"
    assert not (tmp_path / "management.db").exists()
    assert kb_db.execute("SELECT COUNT(*) AS count FROM kb_entities").fetchone()["count"] >= 2
    assert kb_db.execute("SELECT COUNT(*) AS count FROM kb_relations").fetchone()["count"] == 1


def test_standalone_sweep_enqueues_due_connectors_without_platform_cron(tmp_path) -> None:
    from fleetent import kb_ingest_jobs
    from fleetent.knowledge_base.service_config import load_kb_service_config
    from fleetent.knowledge_base.standalone_sweep import sweep

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    config = load_kb_service_config(path)
    queue_url = config.queue_database_url()

    sweep(config, queue_database_url=queue_url)

    job = kb_ingest_jobs.claim_next_job(database_url=queue_url)
    assert job is not None
    payload = json.loads(str(job["connector_ref"]))
    assert payload["connector_id"] == "drive-a"


def test_worker_run_sweeps_due_connectors_without_kb_serve(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import kb_ingest_jobs
    from fleetent.knowledge_base import worker
    from fleetent.knowledge_base.service_config import load_kb_service_config

    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())
    config = load_kb_service_config(path)
    queue_url = config.queue_database_url()

    def fake_run_once(*, queue_database_url=None, data_dir=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(worker, "run_once", fake_run_once)

    with pytest.raises(KeyboardInterrupt):
        worker.run(
            poll_interval=0.01,
            queue_database_url=queue_url,
            data_dir=config.data_dir(),
            standalone_config=config,
        )

    job = kb_ingest_jobs.claim_next_job(database_url=queue_url)
    assert job is not None
    payload = json.loads(str(job["connector_ref"]))
    assert payload["connector_id"] == "drive-a"


def test_standalone_sweep_is_best_effort_when_one_connector_enqueue_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import kb_ingest_jobs
    from fleetent.knowledge_base import standalone_sweep
    from fleetent.knowledge_base.service_config import load_kb_service_config

    path = tmp_path / "kb-service.yaml"
    doc = _service_doc()
    doc["connectors"].append(  # type: ignore[index]
        {
            "id": "drive-b",
            "type": "google_drive",
            "enabled": True,
            "kb_id": "kb-a",
            "folder_id": "folder-2",
            "recursive": True,
            "credential_ref": "env:KB_SHARED_GOOGLE_DRIVE",
            "sync_interval_seconds": 1800,
        }
    )
    _write_yaml(path, doc)
    config = load_kb_service_config(path)
    queue_url = config.queue_database_url()

    original = kb_ingest_jobs.enqueue_connector_job

    def flaky_enqueue(row, *, max_attempts=3, database_url=None):
        if row["connector_id"] == "drive-a":
            raise RuntimeError("boom")
        return original(row, max_attempts=max_attempts, database_url=database_url)

    monkeypatch.setattr(standalone_sweep.kb_ingest_jobs, "enqueue_connector_job", flaky_enqueue)

    standalone_sweep.sweep(config, queue_database_url=queue_url)

    job = kb_ingest_jobs.claim_next_job(database_url=queue_url)
    assert job is not None
    payload = json.loads(str(job["connector_ref"]))
    assert payload["connector_id"] == "drive-b"


def test_standalone_kb_service_runs_without_platform_management_db(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent import kb_ingest_jobs, vector_store
    from fleetent.knowledge_base import serve, worker
    from fleetent.knowledge_base.core.migrations import MIGRATIONS as KB_MIGRATIONS
    from fleetent.knowledge_base.management.runtime import create_knowledge_base
    from fleetent.knowledge_base.service_config import (
        load_kb_service_config,
        validate_kb_service_boot,
    )
    from fleetent.knowledge_base.standalone_sweep import sweep

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "FLEETENT_KB_SERVICE_KEY=svc-test",
                'KB_SHARED_GOOGLE_DRIVE={"client_email":"svc@example.com"}',
                "KB_CONFLUENCE_USERNAME=bot@example.com",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    path = tmp_path / "kb-service.yaml"
    doc = _service_doc()
    doc["connectors"] = [doc["connectors"][0]]  # type: ignore[index]
    _write_yaml(path, doc)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = load_kb_service_config(path)
    validate_kb_service_boot(config)

    queue_url = config.queue_database_url()
    data_dir = config.data_dir()

    async def embed_text(text: str) -> list[float]:
        return [float(len(text)), 0.0]

    async def fake_sync_google_drive(connector_config, *, client):
        from fleetent.knowledge_base.connectors.google_drive import GoogleDriveSyncSummary

        return GoogleDriveSyncSummary(scanned=1, planned=1, ingested=0)

    monkeypatch.setattr(vector_store, "embed_text", embed_text)
    monkeypatch.setattr(worker.knowledge_base, "sync_google_drive", fake_sync_google_drive)
    create_knowledge_base(
        "tenant-a",
        "kb-a",
        "Standalone KB",
        database=worker._knowledge_database(
            "tenant-a", data_dir=data_dir, migrations=KB_MIGRATIONS
        ),
    )

    sweep(config, queue_database_url=queue_url)
    connector_result = worker.run_once(queue_database_url=queue_url, data_dir=data_dir)
    assert connector_result is not None
    assert connector_result["status"] == "done"

    ingest_job = kb_ingest_jobs.enqueue_job(
        job_type="import_document",
        tenant_id="tenant-a",
        kb_id="kb-a",
        connector_ref={
            "source": "guide.md",
            "content": "# Runbook\nStandalone knowledge works.",
            "document_format": "markdown",
        },
        database_url=queue_url,
    )
    ingest_result = worker.run_once(queue_database_url=queue_url, data_dir=data_dir)
    assert ingest_result == {"job_id": ingest_job["id"], "status": "done"}

    app = serve.create_app(
        serve.KBServeConfig(
            tenant_id=config.service.tenant_id,
            service_key_ref=config.service.service_key_ref,
            host=config.service.host,
            port=config.service.port,
            default_mode=config.retrieval.default_mode,
            data_dir=data_dir,
        )
    )
    with TestClient(app, raise_server_exceptions=True) as client:
        response = client.post(
            "/search",
            json={
                "principal": {"user_id": "user-1", "tenant_id": "tenant-a"},
                "query": "Standalone knowledge",
                "kb_ids": ["kb-a"],
                "limit": 3,
            },
            headers={
                "Authorization": "Bearer svc-test",
                "X-Fleetent-Principal": '{"user_id":"user-1","tenant_id":"tenant-a"}',
            },
        )

        assert response.status_code == 200
        assert response.json()["chunks"][0]["filename"] == "guide.md"
    assert not (tmp_path / "management.db").exists()


def test_worker_main_uses_shared_kb_service_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.knowledge_base import worker

    service_dir = tmp_path / "tenants" / "tenant-a" / "kb"
    service_dir.mkdir(parents=True)
    (service_dir / ".env").write_text("KB_SHARED_GOOGLE_DRIVE=shared-secret\n", encoding="utf-8")
    path = service_dir / "kb-service.yaml"
    doc = _service_doc()
    doc["connectors"] = []  # type: ignore[index]
    _write_yaml(path, doc)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    calls: list[tuple[float, str | None, Path | None, object | None]] = []

    def fake_run(
        *,
        poll_interval: float,
        queue_database_url: str | None,
        data_dir: Path | None,
        standalone_config=None,
    ) -> None:
        calls.append((poll_interval, queue_database_url, data_dir, standalone_config))

    monkeypatch.setattr(worker, "run", fake_run)
    monkeypatch.setattr("fleetent.build_info.log_service_startup", lambda name: None)

    worker.main(["--config", str(path), "--poll-interval", "0.25"])

    expected_data_dir = (service_dir / "data").resolve()
    assert len(calls) == 1
    assert calls[0][:3] == (
        0.25,
        f"sqlite:///{expected_data_dir / 'kb_ingest_queue.db'}",
        expected_data_dir,
    )
    assert calls[0][3] is not None


def test_serve_main_uses_shared_kb_service_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.knowledge_base import serve

    service_dir = tmp_path / "tenants" / "tenant-a" / "kb"
    service_dir.mkdir(parents=True)
    (service_dir / ".env").write_text("FLEETENT_KB_SERVICE_KEY=svc-test\n", encoding="utf-8")
    path = service_dir / "kb-service.yaml"
    doc = _service_doc()
    doc["connectors"] = []  # type: ignore[index]
    doc["service"]["service_key_ref"] = "env:FLEETENT_KB_SERVICE_KEY"  # type: ignore[index]
    _write_yaml(path, doc)

    created_configs: list[serve.KBServeConfig] = []
    uvicorn_calls: list[tuple[object, str, int]] = []

    def fake_create_app(config: serve.KBServeConfig) -> object:
        created_configs.append(config)
        return {"config": config}

    def fake_uvicorn_run(app: object, *, host: str, port: int) -> None:
        uvicorn_calls.append((app, host, port))

    monkeypatch.setattr(serve, "create_app", fake_create_app)
    monkeypatch.setattr("uvicorn.run", fake_uvicorn_run)

    serve.main(["--config", str(path)])

    expected_data_dir = (service_dir / "data").resolve()
    assert created_configs[0].data_dir == expected_data_dir
    assert (
        created_configs[0].queue_database_url
        == f"sqlite:///{expected_data_dir / 'kb_ingest_queue.db'}"
    )
    assert uvicorn_calls == [({"config": created_configs[0]}, "127.0.0.1", 8768)]


def test_worker_main_applies_standalone_agent_model_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.knowledge_base import worker

    service_dir = tmp_path / "tenants" / "tenant-a" / "kb"
    service_dir.mkdir(parents=True)
    path = service_dir / "kb-service.yaml"
    doc = _service_doc()
    doc["connectors"] = []  # type: ignore[index]
    doc["embedding"]["api_key_env"] = "FLEETENT_KB_EMBEDDING_API_KEY"  # type: ignore[index]
    doc["extraction"] = {  # type: ignore[index]
        "enabled": True,
        "endpoint": "http://llm.example/v1",
        "model": "kb-extract",
        "api_key_env": "FLEETENT_KB_EXTRACTION_API_KEY",
    }
    _write_yaml(path, doc)
    monkeypatch.setenv("FLEETENT_KB_EMBEDDING_API_KEY", "embed-secret")
    monkeypatch.setenv("FLEETENT_KB_EXTRACTION_API_KEY", "extract-secret")
    monkeypatch.setattr(worker, "run", lambda **_kwargs: None)
    monkeypatch.setattr("fleetent.build_info.log_service_startup", lambda name: None)

    configured_agents: list[object] = []
    monkeypatch.setattr(
        "fleetent.agent_config.set_default_agent_for_process",
        lambda agent: configured_agents.append(agent),
        raising=False,
    )

    worker.main(["--config", str(path)])

    assert len(configured_agents) == 1


def test_serve_main_applies_standalone_agent_model_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fleetent.knowledge_base import serve

    service_dir = tmp_path / "tenants" / "tenant-a" / "kb"
    service_dir.mkdir(parents=True)
    (service_dir / ".env").write_text("FLEETENT_KB_SERVICE_KEY=svc-test\n", encoding="utf-8")
    path = service_dir / "kb-service.yaml"
    doc = _service_doc()
    doc["connectors"] = []  # type: ignore[index]
    doc["service"]["service_key_ref"] = "env:FLEETENT_KB_SERVICE_KEY"  # type: ignore[index]
    doc["embedding"]["api_key_env"] = "FLEETENT_KB_EMBEDDING_API_KEY"  # type: ignore[index]
    _write_yaml(path, doc)
    monkeypatch.setenv("FLEETENT_KB_EMBEDDING_API_KEY", "embed-secret")

    monkeypatch.setattr(serve, "create_app", lambda config: {"config": config})
    monkeypatch.setattr("uvicorn.run", lambda *args, **kwargs: None)

    configured_agents: list[object] = []
    monkeypatch.setattr(
        "fleetent.agent_config.set_default_agent_for_process",
        lambda agent: configured_agents.append(agent),
        raising=False,
    )

    serve.main(["--config", str(path)])

    assert len(configured_agents) == 1


async def test_standalone_embedding_runtime_uses_api_key_env_from_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent import agent_config, vector_store
    from fleetent.agent_config import AgentFile, default_models
    from fleetent.knowledge_base.service_config import KBServiceConfig

    monkeypatch.setenv("FLEETENT_KB_EMBEDDING_API_KEY", "embed-secret")
    config = KBServiceConfig.model_validate(
        {
            "service": {
                "tenant_id": "tenant-a",
                "service_key_ref": "env:FLEETENT_KB_SERVICE_KEY",
            },
            "data": {"home": "./data"},
            "embedding": {
                "endpoint": "http://embed.example/v1/embeddings",
                "model": "kb-embed",
                "dimensions": 3,
                "api_key_env": "FLEETENT_KB_EMBEDDING_API_KEY",
            },
        }
    )

    captured: httpx.Request | None = None

    def capture(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    try:
        config.configure_process_runtime()
        with respx.mock:
            respx.post("http://embed.example/v1/embeddings").mock(side_effect=capture)
            vector = await vector_store.embed_text("hello world")
    finally:
        agent_config.set_default_agent_for_process(
            AgentFile(name="", version=0, models=default_models())
        )
        vector_store.configure_from_active_agent()

    assert vector == [0.1, 0.2, 0.3]
    assert captured is not None
    assert captured.headers["authorization"] == "Bearer embed-secret"
