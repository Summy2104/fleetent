from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_wait_for_jobs_prints_terminal_summary(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from fleetent.knowledge_base import extract_cli

    jobs_by_id = {
        "job-1": iter(
            [
                {"id": "job-1", "status": "pending"},
                {
                    "id": "job-1",
                    "status": "done",
                    "connector_ref": (
                        '{"__request__":{"document_id":"doc-1"},'
                        '"__result__":{"documents_scanned":1,"entities_upserted":2,"relations_written":3}}'
                    ),
                },
            ]
        ),
        "job-2": iter(
            [
                {
                    "id": "job-2",
                    "status": "done",
                    "connector_ref": (
                        '{"__request__":{"document_id":"doc-2"},'
                        '"__result__":{"documents_scanned":1,"entities_upserted":4,"relations_written":5}}'
                    ),
                }
            ]
        ),
    }

    monkeypatch.setattr(extract_cli.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        extract_cli.kb_ingest_jobs,
        "get_job",
        lambda job_id, **kwargs: next(jobs_by_id[job_id]),
    )

    extract_cli._wait_for_jobs(["job-1", "job-2"], database_url="sqlite:////tmp/kb_ingest_queue.db")

    assert capsys.readouterr().out == "documents=2 entities=6 relations=8\n"


def test_wait_for_jobs_times_out_with_worker_hint(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from fleetent.knowledge_base import extract_cli

    class _Clock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            self.now += 1.0
            return self.now

    clock = _Clock()
    monkeypatch.setattr(extract_cli.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(extract_cli.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        extract_cli.kb_ingest_jobs,
        "get_job",
        lambda *args, **kwargs: {"id": "job-1", "status": "pending"},
    )

    with pytest.raises(SystemExit) as exc_info:
        extract_cli._wait_for_jobs(
            ["job-1"], database_url="sqlite:////tmp/kb_ingest_queue.db", timeout_seconds=2
        )

    assert exc_info.value.code == 1
    assert "kb-worker" in capsys.readouterr().err


def test_main_enables_extraction_and_enqueues_existing_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.knowledge_base import extract_cli

    config = SimpleNamespace(
        service=SimpleNamespace(tenant_id="tenant-a"),
        data_dir=lambda: SimpleNamespace(),
        queue_database_url=lambda: "sqlite:////tmp/kb-ingest-queue.db",
    )
    enqueued: list[dict[str, object]] = []
    enabled: list[tuple[str, str, bool]] = []

    monkeypatch.setattr(extract_cli, "load_kb_service_config", lambda path: config)
    monkeypatch.setattr(extract_cli, "_require_known_kb", lambda tenant_id, kb_id, data_dir: None)
    monkeypatch.setattr(extract_cli, "_knowledge_database", lambda tenant_id, data_dir: object())
    monkeypatch.setattr(
        extract_cli,
        "list_documents",
        lambda tenant_id, kb_id, database: [
            {"document_id": "doc-1"},
            {"document_id": "doc-2"},
        ],
    )
    monkeypatch.setattr(
        extract_cli,
        "set_extraction_enabled",
        lambda tenant_id, kb_id, enabled_flag, database: enabled.append(
            (tenant_id, kb_id, enabled_flag)
        ),
    )
    monkeypatch.setattr(
        extract_cli.kb_ingest_jobs,
        "enqueue_job",
        lambda **kwargs: enqueued.append(kwargs) or {"id": f"job-{len(enqueued)}"},
    )

    extract_cli.main(["--config", "/tmp/kb-service.yaml", "--kb", "kb-a"])

    assert enabled == [("tenant-a", "kb-a", True)]
    assert enqueued == [
        {
            "job_type": "extraction",
            "tenant_id": "tenant-a",
            "kb_id": "kb-a",
            "connector_ref": {"document_id": "doc-1"},
            "database_url": "sqlite:////tmp/kb-ingest-queue.db",
        },
        {
            "job_type": "extraction",
            "tenant_id": "tenant-a",
            "kb_id": "kb-a",
            "connector_ref": {"document_id": "doc-2"},
            "database_url": "sqlite:////tmp/kb-ingest-queue.db",
        },
    ]


def test_main_reports_missing_kb_without_enqueuing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from fleetent.knowledge_base import extract_cli

    config = SimpleNamespace(
        service=SimpleNamespace(tenant_id="tenant-a"),
        data_dir=lambda: SimpleNamespace(),
        queue_database_url=lambda: "sqlite:////tmp/kb-ingest-queue.db",
    )
    enqueued: list[dict[str, object]] = []

    monkeypatch.setattr(extract_cli, "load_kb_service_config", lambda path: config)
    monkeypatch.setattr(
        extract_cli,
        "_require_known_kb",
        lambda tenant_id, kb_id, data_dir: (_ for _ in ()).throw(
            ValueError("KB 'kb-missing' does not exist for tenant 'tenant-a'. Create it first via POST /admin/kb.")
        ),
    )
    monkeypatch.setattr(
        extract_cli.kb_ingest_jobs,
        "enqueue_job",
        lambda **kwargs: enqueued.append(kwargs) or {"id": "job-1"},
    )

    with pytest.raises(SystemExit) as exc_info:
        extract_cli.main(["--config", "/tmp/kb-service.yaml", "--kb", "kb-missing"])

    assert exc_info.value.code == 1
    assert enqueued == []
    assert "POST /admin/kb" in capsys.readouterr().err
