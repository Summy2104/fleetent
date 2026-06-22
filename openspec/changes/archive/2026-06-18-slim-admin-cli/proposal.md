## Why

`fleetent-admin` 和 `fleetent node start` 是两个独立 binary，与主入口 `fleetent` 并列，造成三个安装点、三套记忆负担。本 change 将所有人工入口收拢到单一 `fleetent` binary，并退役已有 HTTP API 等价路径的 18 条冗余命令。

**前置条件**：本 change 必须在 **`complete-admin-api-coverage`** 落地后执行。审查（2026-06-18）确认 18 条待删命令中有 6 条（observability traces/usage/performance、create-user、rotate-key、set-default-agent）原本**没有可用 HTTP 等价**——`complete-admin-api-coverage` 补齐了这 4 块 API 后，18 条才全部可安全退役。

## What Changes

- **合并 `fleetent-admin` → `fleetent admin` 子命令组**：原 `fleetent-admin <cmd>` 全部改为 `fleetent admin <cmd>`，复用现有 `platform.admin_cli` 实现，只改命名空间与入口。
- **合并 `fleetent node start` → `fleetent node start`**：原 `fleetent node start` 改为 `fleetent node start`，调 `node.app.main()`（node 全部配置经环境变量，无命令行参数需透传）。
- **移除 18 条已被 HTTP API 覆盖的命令**：
  - 用户管理：`create-user`（→ `POST /admin/service-principals`）、`list-users`、`rotate-key`（→ `POST /admin/users/{id}/rotate-key`）、`block-user`（已是 no-op stub）
  - Agent 管理：`update-agent`、`list-agent-versions`、`activate-agent-version`、`show-agent`、`assign-user`、`unassign-user`、`set-default-agent`（→ `PUT /admin/agents/{name}/default`）
  - KB 连接器：`kb connectors list/check/status/sync`
  - 可观测：`observability traces/usage/performance`（→ `GET /admin/observability/{traces,usage,performance}`）
- **保留并迁移到 `fleetent admin` 命名空间的命令**：
  - A 类（bootstrap）：`seed-builtin-admin`、`init-config`、`validate-config`
  - C 类（维护）：`diagnostics export`、`diagnostics retention`、`maintenance memory/vector/reflection`
  - 仍 CLI-only 的管理命令：`tenants`/`create-team`/`set-user-tenant`/`set-approver`、`node register/list/deregister/pin/unpin`、`memory shared *`、`kb extract-entities`（这些有 HTTP API 但 CLI 入口仍保留作运维便利，不在本次删除范围）
- **`fleetent-admin` / `fleetent node start` 降级为 deprecation shim**：保留 `pyproject.toml` 入口，shim 向 **stderr** 打印迁移提示后转发到新命令。**BREAKING**（带迁移路径）。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities

- `agent-runtime-cli`：新增 `fleetent admin` 子命令组、`fleetent node start`；记录 shim 行为；REMOVE 18 条冗余命令。
- `observability`：REMOVE 三条 observability 查询 CLI 要求（迁移到 `complete-admin-api-coverage` 的 HTTP 端点）。
- `knowledge-base`：REMOVE `kb connectors` CLI 要求（迁移到现有 `/admin/kb/connectors/*`）。
- `agent-definition`：assign-user/unassign-user 由 CLI 改为 HTTP `bindings` 端点。
- `module-boundaries`：MODIFY console-script 指向场景（`fleetent-admin` 指向 shim，非 `admin_cli.main:main`）。

> default-agent spec 由前置 change `complete-admin-api-coverage` 改为控制面属性并注明 CLI 由本 change 移除，本 change 不再重复 default-agent delta。

## Impact

**owning package**：`src/fleetent/__main__.py`（新增 `admin`/`node` 子命令调度）、`src/fleetent/platform/admin_cli/`（`main()` 参数化 + 删 B 类命令）、`src/fleetent/_shims.py`（新建）、`pyproject.toml`（scripts 改 shim）

**public API surface**：无 HTTP 变更；CLI 命名空间变更（`fleetent-admin` → `fleetent admin`，`fleetent node start` → `fleetent node start`）

**owned tables**：无　**config namespace**：无

**cross-module dependencies**：`__main__.py` 懒加载 `platform.admin_cli.main` 与 `node.app`（仅进入对应子命令时触发，不影响 `fleetent agent run` 启动路径）

**下游引用同步（重头工作，非入口本身）**：全仓约 242 处 `fleetent-admin`/`fleetent node start` 引用，本 change 须同步：
- 测试：`tests/unit/test_admin_entrypoint_cleanup.py`（硬断言旧入口）、`tests/integration/test_deployment_docs.py`（断言已删命令串）、各 `patch("sys.argv", ["fleetent-admin", ...])` 的 integration 测试、`test_create_user_new_track.py`（测被删命令）
- specs delta：见上 Modified Capabilities
- 文档：`README.md`、`AGENTS.md`、`docs/operations/*`、`docs/capabilities/*`（被删命令处改指 HTTP API；命名空间处改 `fleetent admin`）
- 脚本/构建：`Makefile` 的 `admin` target、`scripts/install*.sh`

**migration / shim plan**：`fleetent-admin`/`fleetent node start` 保留 shim 一个版本周期，stderr 打印迁移提示后透传；下个 major 删 shim。
