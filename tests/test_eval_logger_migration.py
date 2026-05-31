from pathlib import Path


def test_legacy_eval_logger_import_aliases_observability_module(
    tmp_path: Path, monkeypatch
) -> None:
    import fleetent.eval_logger as legacy
    import fleetent.observability.eval_logger as migrated

    assert legacy is migrated

    trace_path = tmp_path / "traces.jsonl"
    monkeypatch.setattr(legacy, "_LOG_PATH", trace_path)

    migrated.log_run("hi", "hello", [], 0.1)

    assert trace_path.exists()
