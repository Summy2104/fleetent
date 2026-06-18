## Why

`fleetent-admin` 和 `fleetent-node` 是两个独立 binary，与主入口 `fleetent` 并列，造成三个安装点、三套记忆负担。`add-platform-admin-apis` 落地后，18 条 B 类 CLI 命令已有 HTTP API 等价路径，可以移除。本 change 将所有人工入口收拢到单一 `fleetent` binary，并清理已覆盖的冗余 CLI 命令。

**前置条件**：本 change 必须在 `add-platform-admin-apis` 落地后执行。

## What Changes

- **合并 `fleetent-admin` → `fleetent admin` 子命令组**：原 `fleetent-admin <cmd>` 全部改为 `fleetent admin <cmd>`，实现不变，只改命名空间。
- **合并 `fleetent-node` → `fleetent node start`**：原 `fleetent-node` 改为 `fleetent node start`，`fleetent node status` 等子命令视需要一并收入。
- **移除 18 条 B 类冗余命令**（HTTP API 已覆盖，`add-platform-admin-apis` 后可删）：
  - 用户管理：`create-user`、`list-users`、`rotate-key`、`block-user`
  - Agent 管理：`update-agent`、`list-agent-versions`、`activate-agent-version`、`show-agent`、`assign-user`、`unassign-user`、`set-default-agent`
  - KB 连接器：`kb connectors list/check/status/sync`
  - 可观测：`observability traces`、`observability usage`、`observability performance`
- **保留 A 类（bootstrap）和 C 类（维护）命令**，迁移到 `fleetent admin` 命名空间下：
  - A 类：`fleetent admin seed`、`fleetent admin init-config`、`fleetent admin validate-config`
  - B 类（暂留，等 API 就绪后删）→ 本 change 已删，API 先行
  - C 类：`fleetent admin diagnostics export`、`fleetent admin diagnostics retention`、`fleetent admin maintenance memory/vector/reflection`
  - 暂留中（B 类 API 补完）：`fleetent admin tenants`、`fleetent admin nodes`、`fleetent admin memory shared`、`fleetent admin kb extract-entities`
- **`fleetent-admin` 和 `fleetent-node` 降级为 deprecation shim**：`pyproject.toml` 中两个脚本条目改为 shim 函数（打印迁移提示 + 转发到新命令），保留一个版本周期后删除。**BREAKING**（带迁移路径）：`fleetent-admin <cmd>` 运行时打印 `Deprecated: use fleetent admin <cmd>` 后继续执行。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities

- `agent-runtime-cli`：扩展 `fleetent` CLI 入口文档，新增 `fleetent admin` 子命令组（含 A/C 类命令清单）和 `fleetent node start` 子命令；记录 `fleetent-admin`/`fleetent-node` deprecation shim 行为。

## Impact

**owning package**：`src/fleetent/__main__.py`（新增 `admin`/`node` 子命令调度）、`src/fleetent/platform/admin_cli/`（重用现有实现，只改入口）、`pyproject.toml`（scripts 改为 shim）

**public API surface**：无 HTTP API 变更；CLI 命名空间变更（`fleetent-admin` → `fleetent admin`，`fleetent-node` → `fleetent node start`）

**owned tables**：无

**config namespace**：无

**cross-module dependencies**：`__main__.py` 新增对 `platform.admin_cli.main` 和 `node.app` 的懒加载调用（仅在对应子命令时触发，不影响 agent runtime 启动路径）

**migration / shim plan**：`fleetent-admin`/`fleetent-node` 保留为 shim 一个版本，打印迁移提示后透传到新命令；下个 major 版本删除 shim。
