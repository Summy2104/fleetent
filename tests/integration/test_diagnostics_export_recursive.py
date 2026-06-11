"""Diagnostics export excludes SQLite libraries recursively (persistence layer #3).

Per-tenant and per-agent libraries now live in subdirectories of the data
directory. The forbidden-skip enumeration must recurse the whole tree so no
nested ``*.db`` (or its WAL sidecars) leaks into the package, and the manifest
must record every skipped library — including those under subdirectories.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from fleetent.observability.diagnostics import DiagnosticsExportRequest, export_diagnostics


def _manifest_skips(package_path: Path) -> dict[str, str]:
    with zipfile.ZipFile(package_path) as archive:
        manifest = json.loads(archive.read("manifest.json").decode())
    return {item["name"]: item["reason"] for item in manifest["skipped_artifacts"]}


def test_export_excludes_nested_databases_and_records_each_in_manifest(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    # Top-level management library plus nested per-tenant / per-agent libraries.
    (data_dir).mkdir()
    (data_dir / "management.db").write_text("mgmt")
    (data_dir / "tenantA").mkdir()
    (data_dir / "tenantA" / "kb.db").write_text("kb body")
    (data_dir / "tenantA" / "kb.db-wal").write_text("kb wal")
    (data_dir / "tenantA" / "agent1").mkdir()
    (data_dir / "tenantA" / "agent1" / "agent_state.db").write_text("agent state")
    (data_dir / "tenantA" / "agent1" / "agent_state.db-shm").write_text("agent shm")

    package = export_diagnostics(
        DiagnosticsExportRequest(
            output_dir=tmp_path / "exports",
            data_dir=data_dir,
            include_logs=False,
            include_traces=False,
            include_connector_status=False,
        )
    )

    with zipfile.ZipFile(package.path) as archive:
        names = archive.namelist()
    # No nested library content is carried out in the package.
    assert all(".db" not in name for name in names)

    skipped = _manifest_skips(package.path)
    # Every library at every depth is recorded as skipped, with its subdirectory path.
    assert skipped["data/management.db"] == "sqlite database excluded"
    assert skipped["data/tenantA/kb.db"] == "sqlite database excluded"
    assert skipped["data/tenantA/kb.db-wal"] == "sqlite database excluded"
    assert skipped["data/tenantA/agent1/agent_state.db"] == "sqlite database excluded"
    assert skipped["data/tenantA/agent1/agent_state.db-shm"] == "sqlite database excluded"
