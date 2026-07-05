from __future__ import annotations

import os
from pathlib import Path

import yaml


def _write_yaml(path: Path, doc: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def test_load_host_service_config_parses_shared_host_settings(tmp_path: Path) -> None:
    from fleetent.knowledge_base.service_config import load_host_service_config

    config_path = tmp_path / "kb-service.yaml"
    _write_yaml(
        config_path,
        {
            "service": {
                "service_key_ref": "env:FLEETENT_KB_SERVICE_KEY",
                "host": "0.0.0.0",
                "port": 9876,
            },
            "embedding": {
                "endpoint": "http://127.0.0.1:9100/v1/embeddings",
                "model": "bge-m3",
                "dimensions": 1024,
                "api_key_env": "EMBEDDING_API_KEY",
            },
            "rerank": {
                "backend": "http",
                "endpoint": "http://127.0.0.1:9200/v1/rerank",
                "model": "bge-reranker-v2",
                "api_key_env": "RERANK_API_KEY",
            },
            "extraction": {
                "enabled": True,
                "endpoint": "http://127.0.0.1:9300/v1",
                "model": "qwen3-32b",
                "api_key_env": "EXTRACTION_API_KEY",
            },
            "retrieval": {
                "default_mode": "hybrid",
                "top_k": 25,
            },
            "chunking": {
                "chunk_size": 600,
                "chunk_overlap": 80,
            },
        },
    )

    config = load_host_service_config(config_path)

    assert config.service.service_key_ref == "env:FLEETENT_KB_SERVICE_KEY"
    assert config.service.host == "0.0.0.0"
    assert config.service.port == 9876
    assert config.embedding.model == "bge-m3"
    assert config.rerank.model == "bge-reranker-v2"
    assert config.extraction.model == "qwen3-32b"
    assert config.retrieval.top_k == 25
    assert config.chunking.chunk_size == 600


def test_load_tenant_connectors_reads_connectors_yaml_and_env(tmp_path: Path, monkeypatch) -> None:
    from fleetent.knowledge_base.service_config import load_tenant_connectors

    home_dir = tmp_path
    tenant_dir = home_dir / "tenants" / "acme" / "kb"
    _write_yaml(
        tenant_dir / "connectors.yaml",
        {
            "connectors": [
                {
                    "id": "drive-docs",
                    "type": "google_drive",
                    "enabled": True,
                    "kb_id": "support-kb",
                    "folder_id": "folder-123",
                    "access_token_env": "GOOGLE_DRIVE_ACCESS_TOKEN",
                    "refresh_token_env": "GOOGLE_DRIVE_REFRESH_TOKEN",
                }
            ]
        },
    )
    tenant_dir.joinpath(".env").write_text(
        "GOOGLE_DRIVE_ACCESS_TOKEN=token-a\nGOOGLE_DRIVE_REFRESH_TOKEN=refresh-a\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GOOGLE_DRIVE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("GOOGLE_DRIVE_REFRESH_TOKEN", raising=False)

    connectors, tenant_env = load_tenant_connectors(home_dir, "acme")

    assert [connector.id for connector in connectors] == ["drive-docs"]
    assert connectors[0].kb_id == "support-kb"
    assert connectors[0].folder_id == "folder-123"
    assert connectors[0].access_token_env == "GOOGLE_DRIVE_ACCESS_TOKEN"
    assert connectors[0].refresh_token_env == "GOOGLE_DRIVE_REFRESH_TOKEN"
    assert tenant_env == {
        "GOOGLE_DRIVE_ACCESS_TOKEN": "token-a",
        "GOOGLE_DRIVE_REFRESH_TOKEN": "refresh-a",
    }
    assert "GOOGLE_DRIVE_ACCESS_TOKEN" not in os.environ
    assert "GOOGLE_DRIVE_REFRESH_TOKEN" not in os.environ


def test_discover_tenants_scans_tenant_kb_databases(tmp_path: Path) -> None:
    from fleetent.knowledge_base.service_config import discover_tenants

    for tenant_id in ("tenant-b", "tenant-a"):
        kb_db = tmp_path / "tenants" / tenant_id / "kb" / "data" / "kb.db"
        kb_db.parent.mkdir(parents=True, exist_ok=True)
        kb_db.write_text("", encoding="utf-8")
    ignored = tmp_path / "tenants" / "tenant-c" / "kb" / "data"
    ignored.mkdir(parents=True, exist_ok=True)

    assert discover_tenants(tmp_path) == ["tenant-a", "tenant-b"]


def test_host_service_section_accepts_upload_cap(tmp_path: Path) -> None:
    from fleetent.knowledge_base.service_config import load_host_service_config

    config_path = tmp_path / "kb-service.yaml"
    _write_yaml(
        config_path,
        {
            "service": {
                "service_key_ref": "env:FLEETENT_KB_SERVICE_KEY",
                "max_upload_bytes": 1234,
            },
            "embedding": {
                "endpoint": "http://127.0.0.1:9100/v1/embeddings",
                "model": "bge-m3",
                "dimensions": 1024,
            },
        },
    )

    config = load_host_service_config(config_path)

    assert config.service.max_upload_bytes == 1234


def test_repo_template_parses_in_host_mode() -> None:
    """kb-service.yaml.example is what `kb init-config` scaffolds and what
    `make kb-serve`/compose consume in host mode — template↔model drift here
    means neither KB service can boot."""
    from fleetent.knowledge_base.service_config import load_host_service_config

    template = Path(__file__).resolve().parents[2] / "kb-service.yaml.example"

    config = load_host_service_config(template)

    assert config.service.service_key_ref.startswith("env:")


def test_serve_main_passes_upload_cap_from_yaml(tmp_path: Path, monkeypatch) -> None:
    import uvicorn

    from fleetent.knowledge_base import serve

    config_path = tmp_path / "kb-service.yaml"
    _write_yaml(
        config_path,
        {
            "service": {
                "service_key_ref": "env:FLEETENT_KB_SERVICE_KEY",
                "max_upload_bytes": 1234,
            },
            "embedding": {
                "endpoint": "http://127.0.0.1:9100/v1/embeddings",
                "model": "bge-m3",
                "dimensions": 1024,
            },
        },
    )

    captured: dict[str, object] = {}
    monkeypatch.setattr(serve, "create_app", lambda cfg: captured.setdefault("config", cfg))
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: None)

    serve.main(["--config", str(config_path)])

    assert captured["config"].max_upload_bytes == 1234
