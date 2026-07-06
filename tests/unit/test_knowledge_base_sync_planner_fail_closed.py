from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class _FakeDocument:
    id: str


class _FakeStateStore:
    def __init__(self, database) -> None:
        del database
        self.upserts: list[object] = []
        self.deletes: list[tuple[str, str, str, str]] = []

    def upsert(self, state) -> None:
        self.upserts.append(state)

    def delete(self, source_id: str, tenant_id: str, kb_id: str, source_path: str) -> None:
        self.deletes.append((source_id, tenant_id, kb_id, source_path))


class _FakeLogger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def error(self, event: str, **kwargs: object) -> None:
        self.calls.append((event, kwargs))


def _plan_item(sync_planner_module, root: Path, name: str):
    path = root / name
    return sync_planner_module.SyncPlanItem(
        action=sync_planner_module.SyncAction.INGEST_NEW,
        source_id="local-docs",
        tenant_id="tenant-a",
        kb_id="support",
        source_path=str(path.resolve()),
        filename=name,
        document_format="markdown",
        mtime_ns=path.stat().st_mtime_ns,
        content_hash=f"hash-{name}",
    )


@pytest.mark.asyncio
async def test_execute_sync_plan_records_redacted_errors_and_logs_source_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fleetent.knowledge_base import sync_planner
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

    root = tmp_path / "docs"
    root.mkdir()
    for index in range(sync_planner._MAX_RECORDED_ERRORS + 2):
        (root / f"bad-{index}.md").write_text(f"# Bad {index}\nsecret token: tok-{index}", encoding="utf-8")
    good_path = root / "good.md"
    good_path.write_text("# Good\nsafe", encoding="utf-8")

    fake_store = _FakeStateStore(database=None)
    fake_logger = _FakeLogger()
    monkeypatch.setattr(sync_planner, "LocalSourceStateStore", lambda database: fake_store)
    monkeypatch.setattr(sync_planner.runtime, "_database", lambda: object())
    monkeypatch.setattr(sync_planner, "_logger", fake_logger)

    async def fake_ingest(parsed, *, tenant_id, kb_id, source, source_url):
        del tenant_id, kb_id, source
        if parsed.filename.startswith("bad-"):
            raise RuntimeError(f"token: tok-{parsed.filename}")
        return _FakeDocument(id=f"doc:{parsed.filename}")

    monkeypatch.setattr(sync_planner.runtime, "ingest_parsed", fake_ingest)

    items = [_plan_item(sync_planner, root, f"bad-{index}.md") for index in range(sync_planner._MAX_RECORDED_ERRORS + 2)]
    items.append(_plan_item(sync_planner, root, "good.md"))
    plan = sync_planner.SyncPlan(
        source_config=LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
        items=items,
        summary=sync_planner.SyncPlanSummary(scanned=len(items), planned=len(items), ingested=len(items)),
    )

    summary = await sync_planner.execute_sync_plan(plan)

    assert summary.ingested == 1
    assert summary.failed == sync_planner._MAX_RECORDED_ERRORS + 2
    assert len(summary.errors) == sync_planner._MAX_RECORDED_ERRORS
    assert "token [REDACTED]" in summary.errors[0]
    assert "bad-0.md" in summary.errors[0]
    assert fake_store.upserts and fake_store.upserts[0].document_id == "doc:good.md"
    assert len(fake_logger.calls) == sync_planner._MAX_RECORDED_ERRORS + 2
    assert fake_logger.calls[0][0] == "kb_sync_file_failed"
    assert fake_logger.calls[0][1]["source_path"] == str((root / "bad-0.md").resolve())
    assert isinstance(fake_logger.calls[0][1]["exception"], RuntimeError)


@pytest.mark.asyncio
async def test_execute_sync_plan_redacts_connector_like_error_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from fleetent.knowledge_base import sync_planner
    from fleetent.knowledge_base.connectors import LocalDirectorySourceConfig

    root = tmp_path / "docs"
    root.mkdir()
    bad_path = root / "bad.md"
    bad_path.write_text("# Bad\nbody", encoding="utf-8")

    monkeypatch.setattr(sync_planner, "LocalSourceStateStore", lambda database: _FakeStateStore(database))
    monkeypatch.setattr(sync_planner.runtime, "_database", lambda: object())
    monkeypatch.setattr(sync_planner, "_logger", _FakeLogger())

    async def fake_ingest(parsed, *, tenant_id, kb_id, source, source_url):
        del parsed, tenant_id, kb_id, source, source_url
        raise RuntimeError("connector token: xyz")

    monkeypatch.setattr(sync_planner.runtime, "ingest_parsed", fake_ingest)

    plan = sync_planner.SyncPlan(
        source_config=LocalDirectorySourceConfig(
            source_id="local-docs",
            root_path=root,
            allowed_roots=[root],
        ),
        tenant_id="tenant-a",
        kb_id="support",
        items=[_plan_item(sync_planner, root, "bad.md")],
        summary=sync_planner.SyncPlanSummary(scanned=1, planned=1, ingested=1),
    )

    summary = await sync_planner.execute_sync_plan(plan)

    assert summary.failed == 1
    assert summary.errors == [f"{bad_path.resolve()}: connector token [REDACTED]"]
