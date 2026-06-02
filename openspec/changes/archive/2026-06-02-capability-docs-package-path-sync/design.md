## Context

当前 docs 中仍有 legacy 模块名残留：

- `memory_layer`
- `mcp_client`
- `sandbox_client`
- `permission_gate`
- `agent_policy`
- `admin`

这些名字有两种语境：

1. 历史设计或 archive 记录：不需要改。
2. 当前能力文档、架构文档和依赖图：应该改成 canonical package。

本 change 聚焦第二类。

## Canonical Naming

文档应使用以下 canonical package 名称：

| Legacy name | Canonical docs wording |
| --- | --- |
| `memory_layer` | `fleetent.intelligence.memory` 或 `intelligence.memory` |
| `mcp_client` | `fleetent.integrations.mcp` 或 `integrations.mcp` |
| `sandbox_client` | `fleetent.integrations.sandbox` 或 `integrations.sandbox` |
| `permission_gate` | `fleetent.governance.permission_gate` 或 `governance.permission_gate` |
| `agent_policy` | `fleetent.governance.agent_policy` 或 `governance.agent_policy` |
| `quota` | `fleetent.governance.quota` 或 `governance.quota` |
| `audit_log` | `fleetent.governance.audit_log` 或 `governance.audit_log` |
| `blocklist` | `fleetent.governance.blocklist` 或 `governance.blocklist` |
| `fleetent.admin` | `fleetent.platform.admin_cli.main` 或 `fleetent-admin` console script |

在 capability docs 中，短名可以使用 `memory.search()`、`governance.permission_gate`，但首次出现应给出完整路径。

## Documents to Review

必须检查并按需更新：

- `docs/architecture.md`
- `docs/README.md`
- `docs/capabilities/memory.md`
- `docs/capabilities/long-term-ctx.md`
- `docs/capabilities/reflection.md`
- `docs/capabilities/vector-store.md`
- `docs/capabilities/mcp.md`
- `docs/capabilities/sandbox.md`
- `docs/capabilities/governance.md`
- `docs/capabilities/tools.md`
- `docs/capabilities/connectors.md`
- `docs/capabilities/im-gateway.md`
- `docs/capabilities/platform.md`
- `docs/capabilities/owner-capability-roadmap.md`

可以检查但不要求修改：

- `docs/glossary.md`：如果术语本身是概念名，例如 `permission_gate`，可以保留；如果描述实现位置，则改。
- `docs/architecture/source-module-organization-roadmap.md`：该文档本身讨论 legacy shim 和迁移状态，可以保留 legacy 文件名，但需要确保当前状态准确。

不修改：

- `docs/archive/**`
- `openspec/changes/archive/**`

## Current Cleanup State

此 change 应按 cleanup 已完成后的状态执行：

- governance / integrations legacy shims 已删除。
- admin entrypoint legacy shim 已删除。
- memory legacy shim 已删除。

因此当前文档不应继续把 legacy import path 描述为当前 public API 或主要实现位置。

允许保留 legacy 名称的场景：

- `docs/archive/**` 历史记录。
- `openspec/changes/archive/**` 历史记录。
- glossary 中作为概念名出现的术语，例如 `permission_gate`，但描述实现位置时应指向 `fleetent.governance.permission_gate`。

## Validation

需要验证：

- 当前 docs 不再把 legacy shim 描述为主要实现位置。
- 当前 docs 不再把已删除 legacy import path 描述为可用 public API。
- `docs/archive/**` 中的历史旧名不参与清理。
- 当前 OpenSpec specs 中不出现过时的 `intelligence-roadmap` 命名。
- `openspec validate 2026-06-02-capability-docs-package-path-sync --strict` 通过。
- `git diff --check` 通过。
