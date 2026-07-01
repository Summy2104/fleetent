from __future__ import annotations

from pathlib import Path

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


def test_kb_create_cli_creates_and_idempotently_keeps_knowledge_base(tmp_path: Path) -> None:
    path = tmp_path / "kb-service.yaml"
    _write_yaml(path, _service_doc())

    from fleetent.knowledge_base import create_cli
    from fleetent.knowledge_base.worker import _knowledge_database

    create_cli.main(["--config", str(path), "--kb", "kb-a", "--description", "Standalone KB"])
    create_cli.main(["--config", str(path), "--kb", "kb-a", "--description", "Standalone KB"])

    kb_db = _knowledge_database("tenant-a", data_dir=tmp_path / "data")
    rows = kb_db.execute(
        """
        SELECT tenant_id, kb_id, description, archived_at
        FROM knowledge_bases
        ORDER BY kb_id ASC
        """
    ).fetchall()

    assert rows == [
        {
            "tenant_id": "tenant-a",
            "kb_id": "kb-a",
            "description": "Standalone KB",
            "archived_at": None,
        }
    ]
