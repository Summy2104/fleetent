## 1. Unit-layer gate false-positives

- [x] 1.1 Establish red: run `uv run python scripts/check_test_layers.py` and confirm it
      flags `test_config.py` and `test_agent_app_data_redirect.py` (`sqlite-database-url`, exit 1)
- [x] 1.2 Switch the precedence-only `DATABASE_URL` values in both files to a
      `postgresql://` scheme (and matching assertions); run the two affected unit tests
      green and confirm `check_test_layers.py` exits 0

## 2. Shared cached migration helper (TDD)

- [x] 2.1 Write failing tests `tests/integration/test_migration_template.py`: (a) helper
      produces a DB whose `sqlite_master` schema is identical to a freshly `upgrade head`
      DB; (b) a second call copies the template instead of re-running Alembic (assert
      `command.upgrade` invoked once via spy); (c) two calls yield distinct, independently
      mutable files. Run `uv run pytest tests/integration/test_migration_template.py -x -q` → red
- [x] 2.2 Implement `tests/integration/_migration_template.py`: `lru_cache`-backed template
      built by one real `upgrade head`, `apply_migrations(db_path)` via `shutil.copy`,
      `atexit` cleanup. Run the same tests → green

## 3. Migrate integration call sites to the shared helper

- [x] 3.1 Make `tests/integration/test_migrations.py` re-export `apply_migrations` from the
      shared module (keep its own step-wise upgrade/downgrade calls intact); run
      `uv run pytest tests/integration/test_migrations.py -x -q` green
- [x] 3.2 Replace the 31 self-defined `apply_migrations` and 2 `_apply_migrations`
      definitions with an import of the shared helper; run each edited file's tests green
- [x] 3.3 Replace remaining inline `command.upgrade(..., "head")` call sites (outside
      `test_migrations.py`) with the shared helper; run affected files green
- [x] 3.4 Point the root `tests/conftest.py` `_apply_migrations`/`isolated_schedule_db`
      at the shared helper; run dependent tests green

## 4. Verify & finalize

- [x] 4.1 Grep residuals: no `def apply_migrations`, `def _apply_migrations`, or
      `command.upgrade(..., "head")` left in `tests/integration` except `test_migrations.py`
- [x] 4.2 Run full `uv run pytest tests/integration -q`; failure set identical to main
      (19 pre-existing, unrelated to this change), wall time 164.6s → 59.8s (~2.75x)
- [x] 4.3 `check_test_layers.py` exits 0; changed files ruff-clean; `tests/unit` (2268)
      and the helper tests green. Full `pytest -x -q` halts only on the 19 pre-existing
      integration failures already present on `main` (AgentFile access/bindings schema,
      deployment-docs provider assertion) — out of scope for this test-infra change
