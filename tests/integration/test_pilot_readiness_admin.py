import json
from types import SimpleNamespace

from tests.integration.test_admin import run_admin


def test_validate_config_cli_json_outputs_deterministic_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    out, _, code = run_admin("validate-config", "--profile", "pilot", "--format", "json")

    payload = json.loads(out)
    assert code == 0
    assert payload["profile"] == "pilot"
    assert payload["final_status"] in {"pass", "warning"}
    assert "items" in payload
    assert "summary" in payload


def test_maintenance_apply_without_yes_fails_before_mutation():
    out, err, code = run_admin("maintenance", "memory", "compact", "apply")

    assert code != 0
    assert "requires --yes" in err
    assert "dry-run" in err
    assert out == ""


def test_maintenance_memory_compact_apply_outputs_audit_reference(monkeypatch):
    from fleetent.platform import maintenance

    monkeypatch.setattr(
        maintenance,
        "compact_memory",
        lambda *, dry_run, actor: maintenance.MaintenanceSummary(
            command="memory compact",
            dry_run=dry_run,
            affected_counts={"memories_compacted": 2},
            audit_ref="trace-memory-1",
        ),
    )

    out, _, code = run_admin(
        "maintenance", "memory", "compact", "apply", "--yes", "--actor", "operator"
    )

    assert code == 0
    assert "dry_run=False" in out
    assert "memories_compacted=2" in out
    assert "audit_ref=trace-memory-1" in out


def test_kb_sync_execute_requires_yes():
    _, err, code = run_admin("maintenance", "kb", "sync", "execute", "--connector-id", "gdrive")

    assert code != 0
    assert "requires --yes" in err


def test_kb_connector_execute_sync_command_removed(monkeypatch):
    from fleetent.knowledge_base import operations

    called = False

    async def run_connector_sync(connector_id, *, dry_run):
        nonlocal called
        called = True
        return SimpleNamespace(
            connector_id=connector_id,
            status="sync_succeeded",
            summary={},
            error=None,
        )

    monkeypatch.setattr(
        operations,
        "get_connector_config",
        lambda connector_id: SimpleNamespace(connector_type="google_drive"),
    )
    monkeypatch.setattr(operations, "run_connector_sync", run_connector_sync)

    out, err, code = run_admin("kb", "connectors", "sync", "gdrive")

    assert code != 0
    assert out == ""
    assert "invalid choice" in err
    assert called is False


def test_kb_connector_execute_sync_command_removed_even_with_old_flags(monkeypatch):
    from fleetent.knowledge_base import operations

    calls: list[tuple[str, bool]] = []

    async def run_connector_sync(connector_id, *, dry_run):
        calls.append((connector_id, dry_run))
        return SimpleNamespace(
            connector_id=connector_id,
            status="sync_succeeded",
            summary={"documents": 1},
            error=None,
        )

    monkeypatch.setenv("FLEETENT_GOOGLE_DRIVE_EXECUTE_SYNC", "1")
    monkeypatch.setattr(
        operations,
        "get_connector_config",
        lambda connector_id: SimpleNamespace(connector_type="google_drive"),
    )
    monkeypatch.setattr(operations, "run_connector_sync", run_connector_sync)

    out, err, code = run_admin(
        "kb",
        "connectors",
        "sync",
        "gdrive",
        "--yes",
        "--pilot-fixture",
    )

    assert code != 0
    assert "invalid choice" in err
    assert calls == []


def test_maintenance_apply_records_trace_evidence(monkeypatch):
    from fleetent.platform import maintenance

    events = []
    monkeypatch.setattr(maintenance, "record_trace_event", events.append, raising=False)

    summary = maintenance.compact_memory(dry_run=False, actor="operator")

    assert summary.audit_ref is not None
    assert summary.audit_ref.startswith("trace:")
    assert len(events) == 1
    assert events[0].event_type == "maintenance_operation"
    assert events[0].payload["command"] == "memory compact"
    assert events[0].payload["actor"] == "operator"


def test_maintenance_dry_run_does_not_record_trace_evidence(monkeypatch):
    from fleetent.platform import maintenance

    events = []
    monkeypatch.setattr(maintenance, "record_trace_event", events.append, raising=False)

    summary = maintenance.compact_memory(dry_run=True, actor="operator")

    assert summary.audit_ref is None
    assert events == []
