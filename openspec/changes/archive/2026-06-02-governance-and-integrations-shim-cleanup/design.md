## Context

Prior OpenSpec changes migrated implementation code into `fleetent.governance` and
`fleetent.integrations`, then kept top-level re-export shims for compatibility. Current active specs still
say those legacy imports must work, and tests still include compatibility assertions for
`fleetent.mcp_client` and `fleetent.sandbox_client`.

This change intentionally narrows scope to shim removal and import rewrites. It must not alter persistent
data ownership, MCP registry behavior, sandbox command execution, permission gate policy, quota checks, or
audit/blocklist storage.

## Target State

The deleted top-level modules are no longer part of the supported public API:

```text
src/fleetent/agent_policy.py       deleted
src/fleetent/audit_log.py          deleted
src/fleetent/blocklist.py          deleted
src/fleetent/permission_gate.py    deleted
src/fleetent/quota.py              deleted
src/fleetent/mcp_client.py         deleted
src/fleetent/sandbox_client.py     deleted
```

Canonical imports are the only first-party paths:

```python
from fleetent.governance.permission_gate import PermissionGate
from fleetent.governance.quota import check_quota
from fleetent.integrations.mcp import McpServerConfig, register_all
from fleetent.integrations.sandbox import SandboxClient
```

## Implementation Strategy

1. Add failing tests that assert canonical imports remain available and each removed legacy module raises
   `ModuleNotFoundError`.
2. Update source and tests to import canonical modules directly.
3. Remove the seven shim files.
4. Update docs and active OpenSpec specs that still describe these shims as supported.

Use structured import rewrites only; do not change function bodies except where a monkeypatch target must
point at the canonical module. Existing tests for governance, MCP, sandbox, server lifecycle, and tools
serve as behavior preservation coverage.

## Risks

- Tests may patch the old shim path; those patches would stop affecting real implementation after shim
  deletion. Rewrite those patches to canonical modules.
- Active specs may continue requiring legacy compatibility if not updated, causing future contributors to
  recreate the shims.
- `from fleetent import memory_layer` style cleanup is intentionally excluded; memory has a separate
  change in this batch.

## Verification

- Red step: run `uv run pytest tests/unit/test_legacy_shim_cleanup.py -x -q` and observe failure because
  legacy modules are still importable.
- Green step: run the same test after deleting shims and rewriting imports.
- Run targeted governance/integrations tests.
- Run module boundary check, ruff format/check, mypy, full pytest, strict OpenSpec validation, and
  `git diff --check`.
