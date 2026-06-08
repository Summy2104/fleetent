## Context

The integration suite builds a migrated SQLite DB per DB-backed test by calling
`command.upgrade(cfg, "head")` over 58 migrations. This logic is copy-pasted: 31 files
define their own `apply_migrations`, 2 define `_apply_migrations`, 39 inline
`command.upgrade`, and 42 import `apply_migrations` from `test_migrations.py`. Total ~195
invocations, ~26s of pure schema construction (PoC: 133ms each). No caching exists.

Two `tests/unit` files (`test_config.py`, `test_agent_app_data_redirect.py`) set a
`sqlite:///` `DATABASE_URL` purely to assert config/env precedence — no DB is opened —
but `scripts/check_test_layers.py` flags them, leaving the gate red on `main`.

## Goals / Non-Goals

**Goals:**
- One shared, process-cached `apply_migrations(db_path)` used by all integration tests.
- Remove the ~33 duplicated migration-helper definitions and inline upgrades.
- Restore `check_test_layers.py` to exit 0 without weakening the rule.
- Zero change to per-test isolation and to migrated schema content.

**Non-Goals:**
- No `src/fleetent/**` runtime changes, no migration content changes.
- Not converting tests to a shared session-scoped DB (each test keeps its own file).
- Not touching `test_migrations.py`'s step-wise upgrade/downgrade calls.

## Decisions

**1. Process-level template cache via `functools.lru_cache`, copied with `shutil.copy`.**
First call runs the real `upgrade head` into a `tempfile.mkdtemp()` template; later calls
copy it. Rationale: SQLite is a single file, so a fully-migrated DB (including the
`alembic_version` row) is reproducible by byte copy — PoC confirmed byte-identical schema
(133 objects) and that copied DBs still support `downgrade`. The template dir is removed
via `atexit`.
- *Alternative — pytest session-scoped fixture:* cleaner lifecycle but can't be consumed
  by the many module-level `apply_migrations` functions without rewriting every call site
  into fixture injection. The cached free function is a drop-in for existing signatures.
- *Alternative — one shared DB across tests:* breaks isolation; rejected.

**2. Single home for the helper: `tests/integration/_migration_template.py`.**
`test_migrations.py` re-exports `apply_migrations` from it so the 42 importers keep working
unchanged. The other ~33 files drop their local definition and import from the shared module.

**3. Gate fix by scheme swap, not allowlist.** Precedence-only tests switch their
`DATABASE_URL` to `postgresql://...`. Keeps the gate strict (no new allowlist entry) and
the assertions test exactly what they did before (which source wins), since no DB is opened.

## Risks / Trade-offs

- **Stale template if migrations change mid-session** → Not a real risk: migrations are
  static files within a test process; the cache lifetime is one process.
- **A test mutates the template instead of its copy** → Mitigated: helper always copies to
  the caller's `db_path`; the template path is private to the module.
- **A copied DB can't be downgraded** → Disproved by PoC: `alembic_version` is copied, so
  downgrade works; regardless, migration-logic tests don't use the cached helper.
- **Large mechanical edit (~70 files) risks missed call sites** → Mitigation: after edits,
  grep for residual `command.upgrade`/`def apply_migrations` in `tests/integration` (except
  `test_migrations.py`) and run the full integration suite.

## Migration Plan

Pure test-code change; no deploy/rollback. Land on a feature branch, verify full
`tests/integration` + `check_test_layers.py` green, then PR.

## Open Questions

None.
