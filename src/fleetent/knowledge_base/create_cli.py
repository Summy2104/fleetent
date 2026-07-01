from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fleetent.knowledge_base.management.runtime import create_knowledge_base
from fleetent.knowledge_base.service_config import load_kb_service_config
from fleetent.knowledge_base.worker import _knowledge_database


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="fleetent kb create")
    parser.add_argument("--config", required=True, help="standalone kb-service.yaml path")
    parser.add_argument("--kb", required=True, help="knowledge base id to create")
    parser.add_argument("--description", default="", help="optional knowledge base description")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    try:
        ns = _parse_args(argv or [])
        config = load_kb_service_config(Path(ns.config).expanduser())
        tenant_id = config.service.tenant_id
        kb_database = _knowledge_database(tenant_id, data_dir=config.data_dir())
        create_knowledge_base(
            tenant_id,
            str(ns.kb),
            str(ns.description),
            database=kb_database,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
