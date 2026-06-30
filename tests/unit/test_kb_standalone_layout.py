from __future__ import annotations

from pathlib import Path


def test_standalone_tenant_router_flattens_kb_files(tmp_path: Path) -> None:
    from fleetent.knowledge_base import serve

    scope = serve._tenant_router(tmp_path).tenant_scope("tenant-a")

    assert scope.kb_db.path == tmp_path / "kb.db"
    assert scope.kb_vector_backend.database_url == f"sqlite:///{tmp_path / 'kb_vectors.db'}"
    assert not (tmp_path / "tenants").exists()


def test_queue_database_url_uses_flat_data_dir(tmp_path: Path) -> None:
    from fleetent.knowledge_base.service_config import (
        KBDataSection,
        KBServiceConfig,
        KBServiceSection,
    )

    config = KBServiceConfig(
        service=KBServiceSection(
            tenant_id="tenant-a", service_key_ref="env:FLEETENT_KB_SERVICE_KEY"
        ),
        data=KBDataSection(home=str(tmp_path)),
    )

    assert config.queue_database_url() == f"sqlite:///{tmp_path / 'kb_ingest_queue.db'}"


def test_multi_tenant_standalone_layout_uses_distinct_tenant_homes(tmp_path: Path) -> None:
    from fleetent.knowledge_base import serve
    from fleetent.knowledge_base.service_config import (
        KBDataSection,
        KBServiceConfig,
        KBServiceSection,
    )

    tenant_a_home = tmp_path / "tenant-a" / "data"
    tenant_b_home = tmp_path / "tenant-b" / "data"
    config_a = KBServiceConfig(
        service=KBServiceSection(
            tenant_id="tenant-a", service_key_ref="env:FLEETENT_KB_SERVICE_KEY"
        ),
        data=KBDataSection(home=str(tenant_a_home)),
    )
    config_b = KBServiceConfig(
        service=KBServiceSection(
            tenant_id="tenant-b", service_key_ref="env:FLEETENT_KB_SERVICE_KEY"
        ),
        data=KBDataSection(home=str(tenant_b_home)),
    )

    scope_a = serve._tenant_router(tenant_a_home).tenant_scope("tenant-a")
    scope_b = serve._tenant_router(tenant_b_home).tenant_scope("tenant-b")

    assert scope_a.kb_db.path == tenant_a_home / "kb.db"
    assert scope_b.kb_db.path == tenant_b_home / "kb.db"
    assert config_a.queue_database_url() != config_b.queue_database_url()
    assert config_a.queue_database_url() == f"sqlite:///{tenant_a_home / 'kb_ingest_queue.db'}"
    assert config_b.queue_database_url() == f"sqlite:///{tenant_b_home / 'kb_ingest_queue.db'}"


def test_standalone_service_config_parses_embedding_and_extraction_api_key_env() -> None:
    from fleetent.knowledge_base.service_config import KBServiceConfig

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
                "dimensions": 384,
                "api_key_env": "FLEETENT_KB_EMBEDDING_API_KEY",
            },
            "extraction": {
                "enabled": True,
                "endpoint": "http://llm.example/v1",
                "model": "kb-extract",
                "api_key_env": "FLEETENT_KB_EXTRACTION_API_KEY",
            },
        }
    )

    assert config.embedding.api_key_env == "FLEETENT_KB_EMBEDDING_API_KEY"
    assert config.extraction.api_key_env == "FLEETENT_KB_EXTRACTION_API_KEY"


def test_standalone_service_config_builds_runtime_model_routes() -> None:
    from fleetent.knowledge_base.service_config import KBServiceConfig
    from fleetent.model import ModelPolicySnapshot

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
                "dimensions": 384,
                "api_key_env": "FLEETENT_KB_EMBEDDING_API_KEY",
            },
            "extraction": {
                "enabled": True,
                "endpoint": "http://llm.example/v1",
                "model": "kb-extract",
                "api_key_env": "FLEETENT_KB_EXTRACTION_API_KEY",
            },
        }
    )

    policy = ModelPolicySnapshot.from_agent(config.standalone_agent())
    embedding_target = policy.resolve("embedding")[0]
    extraction_target = policy.resolve("kb_extraction")[0]

    assert embedding_target.protocol == "http_embedding"
    assert embedding_target.endpoint == "http://embed.example/v1/embeddings"
    assert embedding_target.model == "kb-embed"
    assert embedding_target.api_key_env == "FLEETENT_KB_EMBEDDING_API_KEY"
    assert extraction_target.protocol == "openai_chat"
    assert extraction_target.base_url == "http://llm.example/v1"
    assert extraction_target.model == "kb-extract"
    assert extraction_target.api_key_env == "FLEETENT_KB_EXTRACTION_API_KEY"
