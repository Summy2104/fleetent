## Why

After core ingest and basic parsers exist, the smallest useful connector is local directory import. It fits
on-premises deployments, works with NFS/shared folders, and avoids SaaS auth complexity. This brings
knowledge-base closer to operational use without requiring Confluence/Drive or background sync workers.

## What Changes

- Add `DataSource` / `DocumentRef` boundary for KB connectors if not already present.
- Add local directory data source:
  - configured root path allowlist
  - recursive file listing
  - extension to format mapping for text / markdown / html
  - fetch bytes/content
- Add manual `sync_local_directory(source_id, tenant_id, kb_id)` or equivalent API.
- Track local source state enough to avoid duplicate ingest for unchanged files:
  - source path
  - mtime
  - content hash
- Use basic parsers + core ingest for supported formats.

## Out of Scope

- No scheduler / background worker.
- No Confluence or Google Drive.
- No ACL / per-document permissions.
- No multi-worker locking.
- No deletion propagation beyond explicit local sync behavior defined here.

## Dependencies

- Requires `knowledge-base-core`.
- Requires `knowledge-base-parsers-basic`.

## Impact

- **Code**: adds local connector under `intelligence.knowledge_base.connectors`.
- **Database**: may add source state table via Alembic if core does not already include it.
- **Tests**: use tmp_path local files; never scan arbitrary host paths or `data/`.
