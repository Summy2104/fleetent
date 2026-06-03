import json

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
