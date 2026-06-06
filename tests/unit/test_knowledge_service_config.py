from __future__ import annotations

import pytest
import yaml


def _knowledge_doc() -> dict[str, object]:
    return {
        "knowledge_bases": [
            {
                "id": "support-kb",
                "tenant_id": "acme",
                "name": "Support KB",
                "indexing": {
                    "chunk_size": 800,
                    "chunk_overlap": 120,
                    "parser_profile": "support",
                    "vector_store": "default",
                },
                "sources": [
                    {
                        "id": "support-drive",
                        "type": "google_drive",
                        "enabled": True,
                        "folder_id": "folder-1",
                        "recursive": True,
                        "access_token_env": "FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN",
                        "refresh_token_env": "FLEETENT_GOOGLE_DRIVE_REFRESH_TOKEN",
                        "client_id_env": "FLEETENT_GOOGLE_DRIVE_CLIENT_ID",
                        "client_secret_env": "FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET",
                    },
                    {
                        "id": "support-confluence",
                        "type": "confluence",
                        "enabled": True,
                        "base_url": "https://example.atlassian.net/wiki",
                        "username_env": "FLEETENT_CONFLUENCE_USERNAME",
                        "space_key": "SUPPORT",
                        "include_children": True,
                        "api_token_env": "FLEETENT_CONFLUENCE_TOKEN",
                    },
                ],
                "sync": {"schedule": "*/30 * * * *", "mode": "incremental"},
            }
        ]
    }


def _write_yaml(path, doc: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def test_default_knowledge_config_path_uses_platform_yaml(tmp_path, monkeypatch) -> None:
    from fleetent.intelligence.knowledge_base.config import knowledge_config_path

    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))

    assert knowledge_config_path() == tmp_path / "platform.yaml"


def test_load_knowledge_config_reads_platform_knowledge_section(tmp_path) -> None:
    from fleetent.intelligence.knowledge_base.config import load_knowledge_config

    path = tmp_path / "platform.yaml"
    _write_yaml(path, {"knowledge": _knowledge_doc()})

    snapshot = load_knowledge_config(path)

    assert [kb.id for kb in snapshot.knowledge_bases] == ["support-kb"]
    assert snapshot.knowledge_bases[0].sources[0].id == "support-drive"


def test_load_knowledge_config_parses_sources_and_defaults(tmp_path) -> None:
    from fleetent.intelligence.knowledge_base.config import load_knowledge_config

    path = tmp_path / "knowledge.yaml"
    doc = _knowledge_doc()
    doc["knowledge_bases"].append(  # type: ignore[index, union-attr]
        {
            "id": "billing-kb",
            "tenant_id": "acme",
            "sources": [],
        }
    )
    _write_yaml(path, doc)

    snapshot = load_knowledge_config(path)

    assert [kb.id for kb in snapshot.knowledge_bases] == ["support-kb", "billing-kb"]
    support = snapshot.knowledge_bases[0]
    assert support.indexing.chunk_size == 800
    assert support.indexing.chunk_overlap == 120
    assert support.sync.schedule == "*/30 * * * *"
    assert support.sync.mode == "incremental"
    drive = next(source for source in support.sources if source.id == "support-drive")
    assert drive.type == "google_drive"
    assert drive.tenant_id == "acme"
    assert drive.kb_id == "support-kb"
    assert snapshot.knowledge_bases[1].indexing.chunk_size == 1000
    assert snapshot.knowledge_bases[1].sync.mode == "manual"


def test_duplicate_source_ids_fail_fast(tmp_path) -> None:
    from fleetent.intelligence.knowledge_base.config import load_knowledge_config

    doc = _knowledge_doc()
    sources = doc["knowledge_bases"][0]["sources"]  # type: ignore[index]
    sources[1]["id"] = "support-drive"  # type: ignore[index]
    path = tmp_path / "knowledge.yaml"
    _write_yaml(path, doc)

    with pytest.raises(ValueError, match="duplicate source id: support-drive"):
        load_knowledge_config(path)


@pytest.mark.parametrize(
    ("source_type", "field"),
    [
        ("google_drive", "folder_id"),
        ("confluence", "base_url"),
        ("confluence", "space_key or page_id"),
    ],
)
def test_source_type_required_fields_are_validated(tmp_path, source_type: str, field: str) -> None:
    from fleetent.intelligence.knowledge_base.config import load_knowledge_config

    doc = _knowledge_doc()
    sources = doc["knowledge_bases"][0]["sources"]  # type: ignore[index]
    source = next(item for item in sources if item["type"] == source_type)  # type: ignore[index]
    if field == "space_key or page_id":
        source.pop("space_key", None)
        source.pop("page_id", None)
    else:
        source.pop(field)
    path = tmp_path / "knowledge.yaml"
    _write_yaml(path, doc)

    with pytest.raises(Exception, match=field):
        load_knowledge_config(path)


def test_secret_like_source_values_must_use_env_reference_fields(tmp_path) -> None:
    from fleetent.intelligence.knowledge_base.config import load_knowledge_config

    doc = _knowledge_doc()
    source = doc["knowledge_bases"][0]["sources"][1]  # type: ignore[index]
    source["api_token"] = "secret-token-value"  # type: ignore[index]
    path = tmp_path / "knowledge.yaml"
    _write_yaml(path, doc)

    with pytest.raises(ValueError, match="inline secret-like value"):
        load_knowledge_config(path)


def test_repo_does_not_ship_standalone_knowledge_service_examples() -> None:
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    assert not (repo / "config" / "knowledge.yaml.example").exists()
    assert not (repo / "config" / "knowledge-service").exists()
    assert not (repo / "examples" / "knowledge-service").exists()
