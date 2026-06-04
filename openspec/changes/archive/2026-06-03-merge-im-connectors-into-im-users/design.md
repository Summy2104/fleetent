## Context

Two IM homes share one legacy SQLite DB but live apart:

- `src/fleetent/im_user_store.py` — IM identity mapping + per-identity allowlist
  (`im_users` table). Legacy top-level module, uses `user_store._conn` + `_init_db()`
  with a legacy-rebuild path; mixes `?` and named params.
- `src/fleetent/platform/im_gateway_management/` — `im_connector_store` (`im_connectors`
  table), `im_connector_config` (secret resolution + `.env` seed/mask),
  `im_connector_manager` (async adapter supervisor), `im_channel_allowlist`
  (`im_channel_allowlist` table), `im_admin_api` (`/admin/im` FastAPI router). Same
  legacy `_conn`/`_init_db`/legacy-rebuild pattern.

~13 src + ~17 test files import across both. `module-boundaries` declares a canonical
package map (`channels` is the IM-facing top-level) and the rule "每张持久化表 SHALL
有且只有一个 owner module".

## Goals / Non-Goals

**Goals:**
- One IM module owns all three IM tables and exposes a single public API surface.
- Connector config/secrets, registry/status, manager, channel allowlist, identity
  mapping + allowlist, and the `/admin/im` router all reachable from that module.
- Legacy import paths kept as re-export-only compatibility shims.
- Behavior preserved exactly: no schema change, no route change, no API semantic change.

**Non-Goals:**
- No Alembic migration / table redesign (columns, keys, legacy-rebuild unchanged).
- No migration off the legacy `_conn`/`_init_db` pattern to the DB runtime (separate
  future change — keep this move behavior-preserving).
- No change to HTTP route paths (`/admin/im/*` stay identical).
- No change to adapter logic in `im_gateway/{slack,telegram}.py`.

## Decisions

**D1 — Host module.** Consolidate into the existing canonical platform IM module
`src/fleetent/platform/im_gateway_management/` (the "IM module"), absorbing the
IM-users store into it. The user framed this as "merge into the IM users module";
functionally the host name is cosmetic since the result is one IM module. We pick the
platform IM package as host rather than resurrecting a top-level `im_user_store` god
file, because the canonical package map forbids new top-level feature modules and the
connector code already lives there. The IM-users store moves in as `identity.py`.

**D2 — File layout** (internal names use no leading underscore but are documented as
internal; public API is the package `__init__`):
```
platform/im_gateway_management/
  __init__.py          # public API: re-exports the names below
  identity.py          # ex im_user_store: get_or_create, allowlist, workbench
  connector_store.py   # ex im_connector_store
  connector_config.py  # ex im_connector_config
  connector_manager.py # ex im_connector_manager (ConnectorManager)
  channel_allowlist.py # ex im_channel_allowlist
  admin_api.py         # ex im_admin_api (router, prefix /admin/im)
```

**D3 — Compatibility shims.** Old import paths re-export public names only:
- `fleetent.im_user_store` → re-export from `…im_gateway_management.identity`
- `…im_gateway_management.im_connector_store` → re-export from `connector_store`
  (same for `im_connector_config`, `im_connector_manager`, `im_channel_allowlist`,
  `im_admin_api`).
Shims carry `# noqa: F401` and no logic. This keeps the diff bounded and lets a later
cleanup change delete them once all first-party imports use canonical paths.

**D4 — DB_PATH re-export preserved.** Each store currently re-exports
`user_store.DB_PATH` for test monkeypatching. The consolidated module keeps a single
`DB_PATH` re-export that all submodules and tests use, preserving the existing
isolation pattern (`monkeypatch.setattr(module, "DB_PATH", tmp_path/…)`).

**D5 — Importer migration.** Update first-party src importers to canonical paths;
tests follow. HTTP route registration in `server.py` switches to `admin_api.router`
(path unchanged). `static/admin.html` untouched (calls `/admin/im/*` over HTTP).

**D6 — module-boundaries delta.** Add a scenario/clarification: the unified IM module
is the sole owner of `im_users`, `im_connectors`, `im_channel_allowlist`; legacy paths
are compatibility shims. Records the deliberate coupling of connector secrets with
identity inside one IM module.

## Risks / Trade-offs

- **Coupling secrets with identity.** One module now holds bot tokens and user
  identity. Mitigated by keeping admin_api admin-only + masked reads unchanged, and by
  documenting the boundary in module-boundaries. Accepted per the "全量合并" decision.
- **Large import churn (~30 files).** Mitigated by shims: src/tests can migrate
  incrementally and the suite stays green at each step; behavior-preserving move means
  no test assertions change, only import lines.
- **Two `_init_db()` paths now co-located.** Each table keeps its own `_init_db`; no
  attempt to merge them (would risk altering the legacy-rebuild behavior). Cleanup to
  the DB runtime is a separate change.
- **Circular-import risk** inside the package (`identity` ← `user_store` →
  `im_user_store` shim). Mitigated by lazy `from fleetent import user_store` imports
  (already the pattern) and shims that only re-export.
