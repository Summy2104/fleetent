## Why

The integration suite re-runs the full Alembic `upgrade head` (58 migrations) once
per DB-backed test — 195 invocations across ~70 files — costing ~26s of pure schema
construction with no caching. Separately, two `tests/unit` cases embed
`sqlite:///` `DATABASE_URL` values that only exercise config/env-precedence parsing
(no real DB), which trips `scripts/check_test_layers.py` and leaves the gate red on
`main`. Both are test-infrastructure debt that slows every run and breaks the layer gate.

## What Changes

- Add a shared, process-cached `apply_migrations(db_path)` helper: the first call runs
  the real Alembic upgrade once into a template DB, subsequent calls `shutil.copy` it.
  PoC measured 80x speedup (133ms → 1.7ms), byte-identical schema, unchanged per-test
  isolation (each test still gets its own DB file).
- Migrate all ~70 integration test files to the shared helper, removing the ~33
  duplicated `apply_migrations`/`_apply_migrations` definitions and inline
  `command.upgrade(...)` calls. `tests/integration/test_migrations.py` keeps its own
  step-wise upgrade/downgrade calls (those test migration logic itself).
- Fix the two `tests/unit` gate false-positives by switching the precedence-only
  `DATABASE_URL` values to a non-sqlite scheme (`postgresql://`), restoring
  `check_test_layers.py` to exit 0. Semantics unchanged (no DB is opened).

## Capabilities

### New Capabilities
- `test-infrastructure`: governs how the test suite obtains migrated databases (shared
  cached migration helper) and the unit/integration layer boundary the gate enforces.

### Modified Capabilities
<!-- None: no product/runtime requirement changes. -->

## Impact

- **Tests only** — no `src/fleetent/**` runtime behavior changes, no schema changes,
  no new runtime dependencies.
- New shared helper module under `tests/integration/`.
- ~70 `tests/integration/test_*.py` files edited to use it; 2 `tests/unit` files edited.
- `scripts/check_test_layers.py` gate returns to green.
- Faster local + CI integration runs (~26s saved on schema construction).
