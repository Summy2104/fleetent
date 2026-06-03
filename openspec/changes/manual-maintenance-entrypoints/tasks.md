## 1. Shared summary and confirmation model

- [ ] 1.1 Write failing tests: maintenance command summary supports human text and JSON output with affected counts, dry-run flag and audit reference.
- [ ] 1.2 Implement: shared summary model/helpers.
- [ ] 1.3 Verify green: run `uv run pytest tests/unit -x -q`.

- [ ] 1.4 Write failing tests: destructive operations without `--yes` fail before mutation.
- [ ] 1.5 Implement: shared confirmation guard.
- [ ] 1.6 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

## 2. Maintenance commands

- [ ] 2.1 Write failing tests: memory retention / compaction dry-run and apply output affected counts and write audit/trace on apply.
- [ ] 2.2 Implement: memory maintenance CLI entrypoints via public API.
- [ ] 2.3 Verify green: run `uv run pytest tests/integration -x -q`.

- [ ] 2.4 Write failing tests: KB sync dry-run / execute and vector reindex dry-run / apply / rebuild output source/namespace summaries.
- [ ] 2.5 Implement: KB/vector maintenance CLI entrypoints via public API.
- [ ] 2.6 Verify green: run `uv run pytest tests/integration -x -q`.

- [ ] 2.7 Write failing tests: reflection report run and proposal list / approve / reject / apply output summary and write audit/trace for state changes.
- [ ] 2.8 Implement: reflection maintenance CLI entrypoints via public API.
- [ ] 2.9 Verify green: run `uv run pytest tests/integration -x -q`.

## 3. Report/docs integration

- [ ] 3.1 Write failing tests: pilot verification report can include manual maintenance command evidence when artifacts are provided.
- [ ] 3.2 Implement: optional evidence ingestion or documented artifact path.
- [ ] 3.3 Verify green: run `uv run pytest tests/unit tests/integration -x -q`.

- [ ] 3.4 Write failing docs/check tests if applicable: runbook documents dry-run first and `--yes` requirement.
- [ ] 3.5 Implement: update runbook, intelligence roadmap and platform/channel roadmap as needed.
- [ ] 3.6 Run `uv run ruff format src tests scripts`.
- [ ] 3.7 Run `uv run ruff check src tests scripts`.
- [ ] 3.8 Run `uv run mypy src`.
- [ ] 3.9 Run `uv run pytest -x -q`.
- [ ] 3.10 Run `openspec validate manual-maintenance-entrypoints`.
