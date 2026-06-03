## Why

Pilot readiness safeguards have been implemented and merged, but review found three mismatches that can mislead
operators or block a real Pilot environment:

- `validate-config` currently scans loaded `Settings`, so secrets provided correctly through environment
  variables can be reported as inline config secrets.
- KB connector execute sync documentation describes explicit opt-in and Pilot fixture boundaries, but the manual
  CLI sync path does not enforce those safeguards.
- Manual maintenance apply commands return audit-like strings, but do not create real observability evidence.

These are not new product capabilities. They are corrective hardening for the Pilot delivery safeguards already
specified and archived.

## What Changes

- Change config validation secret scanning to inspect config file sources rather than resolved env-backed settings.
- Add a manual execute-sync gate for `fleetent-admin kb connectors sync <id>` when `--dry-run` is absent.
- Require execute sync confirmation, execute opt-in and explicit Pilot fixture acknowledgement before mutation.
- Record real observability trace evidence for manual maintenance apply commands and return that trace reference.
- Update Pilot deployment docs so the CLI commands match the enforced behavior.

## Capabilities

### Modified Capabilities

- `production-config-validation`: distinguish config-file inline secrets from env-provided secrets.
- `kb-connector-smoke-status`: enforce manual execute-sync safeguards at the CLI boundary.
- `manual-maintenance-entrypoints`: make mutation evidence real trace evidence, not a synthetic placeholder.

## Impact

- **owning package**：`platform` for admin CLI and maintenance entrypoints; `intelligence` for KB connector
  operations; `observability` for trace evidence; config validation remains in `platform`.
- **public API surface**：may add parameters to `validate_config`, `run_connector_sync` / CLI sync handling, and
  maintenance helper functions. Existing CLI dry-run commands remain compatible.
- **owned tables**：no new tables; maintenance evidence uses existing observability trace storage.
- **config namespace**：no new persistent config namespace; execute sync uses explicit CLI flags and env opt-in.
- **cross-module dependencies**：platform may call observability public API to record trace evidence; KB connector
  CLI uses knowledge-base public operations.
- **migration / shim plan**：no schema migration.

## Non-Goals

- Do not implement scheduler / worker / dashboard.
- Do not introduce full RBAC or a new audit log table in this change.
- Do not run real connector sync by default in tests.
