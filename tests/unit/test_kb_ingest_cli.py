from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_wait_for_job_prints_terminal_summary(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from fleetent.knowledge_base import ingest_cli

    states = iter(
        [
            {"id": "job-1", "status": "pending"},
            {
                "id": "job-1",
                "status": "done",
                "connector_ref": (
                    '{"__request__":{"path":"/tmp/docs"},'
                    '"__result__":{"scanned":3,"ingested":2,"skipped":1,"failed":0}}'
                ),
            },
        ]
    )
    monkeypatch.setattr(ingest_cli.time, "sleep", lambda _: None)
    monkeypatch.setattr(ingest_cli.kb_ingest_jobs, "get_job", lambda *args, **kwargs: next(states))

    ingest_cli._wait_for_job("job-1", database_url="sqlite:////tmp/kb_ingest_queue.db")

    assert capsys.readouterr().out == "scanned=3 ingested=2 skipped=1 failed=0\n"


def test_wait_for_job_times_out_with_worker_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from fleetent.knowledge_base import ingest_cli

    class _Clock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            self.now += 1.0
            return self.now

    clock = _Clock()
    monkeypatch.setattr(ingest_cli.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(ingest_cli.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        ingest_cli.kb_ingest_jobs,
        "get_job",
        lambda *args, **kwargs: {"id": "job-1", "status": "pending"},
    )

    with pytest.raises(SystemExit) as exc_info:
        ingest_cli._wait_for_job("job-1", database_url="sqlite:////tmp/kb_ingest_queue.db", timeout_seconds=2)

    assert exc_info.value.code == 1
    assert "kb-worker" in capsys.readouterr().err


def test_main_reports_missing_kb_without_enqueuing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from fleetent.knowledge_base import ingest_cli

    config = SimpleNamespace(
        service=SimpleNamespace(tenant_id="tenant-a"),
        data_dir=lambda: SimpleNamespace(),
        queue_database_url=lambda: "sqlite:////tmp/kb-ingest-queue.db",
    )
    enqueued: list[dict[str, object]] = []

    monkeypatch.setattr(ingest_cli, "load_kb_service_config", lambda path: config)
    monkeypatch.setattr(
        ingest_cli,
        "_require_known_kb",
        lambda tenant_id, kb_id, data_dir: (_ for _ in ()).throw(
            ValueError("KB 'kb-missing' does not exist for tenant 'tenant-a'. Create it first via POST /admin/kb.")
        ),
    )
    monkeypatch.setattr(
        ingest_cli.kb_ingest_jobs,
        "enqueue_job",
        lambda **kwargs: enqueued.append(kwargs) or {"id": "job-1"},
    )

    with pytest.raises(SystemExit) as exc_info:
        ingest_cli.main(["--config", "/tmp/kb-service.yaml", "--kb", "kb-missing", "/tmp/docs"])

    assert exc_info.value.code == 1
    assert enqueued == []
    assert "POST /admin/kb" in capsys.readouterr().err
