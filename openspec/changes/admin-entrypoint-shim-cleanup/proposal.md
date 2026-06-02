## Why

The admin CLI implementation already lives in `fleetent.platform.admin_cli`. The remaining
`src/fleetent/admin.py` file only re-exports `main`, and `pyproject.toml` still routes the
`fleetent-admin` console script through that legacy shim.

Keeping the shim after the platform package split leaves an obsolete public import path in tests, docs, and
packaging metadata. Removing it makes `platform.admin_cli` the single admin CLI entrypoint without changing
CLI behavior.

## What Changes

- Delete `src/fleetent/admin.py`.
- Change `pyproject.toml` console script to:
  - `fleetent-admin = "fleetent.platform.admin_cli.main:main"`
- Update tests and docs that import or describe `fleetent.admin`.
- Add regression coverage proving the console script points at the canonical entrypoint and
  `fleetent.admin` is no longer importable.
- Keep existing `fleetent-admin` command behavior unchanged.

## Out of Scope

- No admin command behavior changes.
- No parser or command domain refactor.
- No user store, IM store, schedule, diagnostics, observability, or KB connector behavior changes.
- No database schema changes.
- No configuration namespace changes.

## Module Boundary Impact

- **Owning package**：`platform`.
- **Public API surface**：
  - `fleetent.platform.admin_cli.main.main` remains the admin CLI entrypoint.
  - `fleetent-admin` console script points directly to `fleetent.platform.admin_cli.main:main`.
  - Removed public legacy path: `fleetent.admin`.
- **Owned tables**：无。
- **Config namespace**：无。
- **Cross-module dependencies**：
  - Admin command modules continue using existing platform/public store APIs.
  - Other modules must not import `fleetent.admin`.
- **Migration / shim plan**：
  - Compatibility shim was created by `2026-06-02-admin-cli-module-split`.
  - This cleanup removes the shim and migrates first-party references to the canonical entrypoint.
