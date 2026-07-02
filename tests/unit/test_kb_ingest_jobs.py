from __future__ import annotations

import pytest

import fleetent.kb_ingest_jobs as kb_ingest_jobs


@pytest.mark.parametrize("database_url", [None, ""])
def test_database_requires_explicit_queue_database_url(
    database_url: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="queue database_url is required"):
        kb_ingest_jobs.get_job("missing", database_url=database_url)  # type: ignore[arg-type]
