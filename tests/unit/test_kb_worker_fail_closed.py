from __future__ import annotations

from fleetent.knowledge_base import worker


def test_sync_job_summary_reads_sync_directory_and_connector_payloads() -> None:
    sync_directory_result = {"scanned": 2, "failed": 1, "errors": ["a"]}
    connector_result = {"summary": {"scanned": 3, "failed": 1, "errors": ["b"]}}

    assert worker._sync_job_summary("sync_directory", sync_directory_result) == sync_directory_result
    assert worker._sync_job_summary("connector_sync", connector_result) == connector_result["summary"]
    assert worker._sync_job_summary("import_document", {"chunks": 1}) is None


def test_sync_terminal_failure_prefers_first_error() -> None:
    summary = {
        "scanned": 2,
        "ingested": 0,
        "failed": 2,
        "errors": ["first failure", "second failure"],
    }

    assert worker._sync_terminal_failure(summary) == "first failure"


def test_sync_completion_error_renders_partial_failure_summary() -> None:
    summary = {
        "scanned": 4,
        "ingested": 2,
        "failed": 2,
        "errors": ["one", "two", "three", "four"],
    }

    assert worker._sync_completion_error(summary) == "one; two; three (+1 more)"


def test_sync_completion_error_falls_back_to_counts_without_error_details() -> None:
    assert worker._sync_completion_error({"scanned": 5, "failed": 2}) == (
        "sync completed with 2 failed item(s) out of 5"
    )
    assert worker._sync_terminal_failure({"scanned": 0, "ingested": 0, "failed": 1}) is None
