## Why

Governance and integrations implementations have already moved into canonical packages:

- `fleetent.governance.*`
- `fleetent.integrations.mcp`
- `fleetent.integrations.sandbox`

The old top-level files are now compatibility shims. Keeping them after internal callers have a canonical
path weakens the module boundary policy because new code can continue importing legacy paths, tests can
monkeypatch shim modules instead of real implementations, and roadmap documentation still describes the
temporary compatibility state as current.

## What Changes

- Delete the migrated governance shims:
  - `src/fleetent/agent_policy.py`
  - `src/fleetent/audit_log.py`
  - `src/fleetent/blocklist.py`
  - `src/fleetent/permission_gate.py`
  - `src/fleetent/quota.py`
- Delete the migrated integrations shims:
  - `src/fleetent/mcp_client.py`
  - `src/fleetent/sandbox_client.py`
- Move source and test imports to canonical paths:
  - `fleetent.governance.*`
  - `fleetent.integrations.mcp`
  - `fleetent.integrations.sandbox`
- Update active specs and architecture docs so they no longer require these legacy import paths.
- Add regression coverage proving the removed legacy modules are no longer importable while canonical
  paths remain available.

## Out of Scope

- No governance behavior changes.
- No MCP transport or tool naming behavior changes.
- No sandbox execution behavior changes.
- No database schema changes.
- No configuration namespace changes.
- No vector, memory, admin CLI, runtime loop, or channel behavior changes.

## Module Boundary Impact

- **Owning package**：`governance` and `integrations`.
- **Public API surface**：
  - Governance public API remains available through `fleetent.governance.*`.
  - MCP public API remains available through `fleetent.integrations.mcp` and
    `fleetent.integrations.mcp.client`.
  - Sandbox public API remains available through `fleetent.integrations.sandbox` and
    `fleetent.integrations.sandbox.client`.
  - Removed public legacy paths: `fleetent.agent_policy`, `fleetent.audit_log`,
    `fleetent.blocklist`, `fleetent.permission_gate`, `fleetent.quota`, `fleetent.mcp_client`,
    `fleetent.sandbox_client`.
- **Owned tables**：无。
- **Config namespace**：无。
- **Cross-module dependencies**：
  - Runtime, platform, channels, and tools must call governance/integrations through canonical public
    APIs.
  - Governance and integrations must not import runtime entrypoints.
- **Migration / shim plan**：
  - Compatibility shims were created by prior package migration changes.
  - This change is the cleanup batch: migrate remaining first-party imports, delete the shims, and
    update specs/docs to make canonical paths the only supported first-party API.
