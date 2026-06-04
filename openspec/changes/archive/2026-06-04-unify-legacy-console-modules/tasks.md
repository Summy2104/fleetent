## 1. Knowledge Base search

- [x] 1.1 Write failing UI assertions in `tests/integration/test_admin_console_ui.py`: KB `.ph-filter` holds a search input (e.g. `id="kb-filter"`) and `loadKb`/render filters by kb_id/description → red
- [x] 1.2 Implement: cache KB rows, add the search input to the KB page header, filter rendered rows live; no-match shows the empty state → green; browser self-test

## 2. Sessions search

- [x] 2.1 Write failing UI assertions: Sessions `.ph-filter` holds a search input (`id="sess-filter"`) and the render filters by session id/user/agent → red
- [x] 2.2 Implement search + cache + empty state for Sessions → green; browser self-test

## 3. Monitoring search

- [x] 3.1 Write failing UI assertions: Monitoring `.ph-filter` holds a search input (`id="mon-filter"`) and the render filters by alert/metric name → red
- [x] 3.2 Implement search + cache + empty state for Monitoring → green; browser self-test

## 4. Statistics search

- [x] 4.1 Write failing UI assertions: Statistics `.ph-filter` holds a search input (`id="st-filter"`) and the per-user render filters by user id/name/email → red
- [x] 4.2 Implement search + cache + empty state for Statistics → green; browser self-test

## 5. Verify

- [x] 5.1 `uv run pytest -x -q` (full suite) green; `uv run ruff check src tests` clean; JS parses (no syntax errors / control chars)
- [x] 5.2 Browser-verify all four modules: search box present, filters rows, no-match shows empty state, clearing restores; consistent with the modern modules
- [x] 5.3 Archive the change on the feature branch (`/opsx:archive`) after all checkboxes are `[x]`
