## Why

`slim-admin-cli` 落地后遗留两类残骸：(1) `admin_cli` 的 `im.py` / `agents.py` 两个模块命令已全删、`register()` 变空壳但仍挂在 `_COMMAND_MODULES`；(2) `fleetent-admin` / `fleetent-node` deprecation shim——经确认内部安装脚本/文档已全部迁移到 `fleetent admin` / `fleetent node start`，无需保留宽限期。本 change 一次清掉，并补回 slim 落地时漏合并的 agent-runtime-cli spec（新入口形态无 spec 覆盖）。

## What Changes

- **删空模块**：从 `admin_cli/main.py` 的 `_COMMAND_MODULES` 移除 `im`、`agents`，删除两个空壳文件 `im.py` / `agents.py`。
- **删 shim（BREAKING，无宽限期）**：从 `pyproject.toml` 移除 `fleetent-admin` 与 `fleetent-node` 两个 `[project.scripts]` 入口，删除 `src/fleetent/_shims.py`。此后 `fleetent-admin` / `fleetent-node` 命令不再存在；管理操作走 `fleetent admin <cmd>`，node supervisor 走 `fleetent node start`。
- **反向清理 slim 加的下游**：删 `tests/unit/test_shims.py`；改 `tests/unit/test_admin_entrypoint_cleanup.py`（断言 `fleetent-admin`/`fleetent-node` 入口**不存在**，而非指向 shim）；改 `tests/integration/test_deployment_docs.py` 中相关断言。
- **补 agent-runtime-cli spec**：新增 `fleetent admin` 子命令组、`fleetent node start` 两条 requirement（slim apply 时未合并，致新入口无 spec 覆盖）。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities

- `agent-runtime-cli`：ADD `fleetent admin` 子命令组与 `fleetent node start` 两条 requirement（记录删 shim 后的正规入口）。
- `module-boundaries`：MODIFY「Admin CLI package split」——`fleetent-admin` console script 入口移除（不再指向 shim）；MODIFY「Capability docs use canonical package names」的 admin 入口场景，改引 `fleetent admin`。
- `install-bootstrap`：MODIFY 安装入口清单——不再安装 `fleetent-admin`（保留 `fleetent`，`fleetent-tui` 由独立的 remove-tui-client 处理）。

## Impact

**owning package**：`src/fleetent/__main__.py`（不变，admin/node 分发已在）、`platform/admin_cli/main.py`、`pyproject.toml`，删除 `src/fleetent/_shims.py`、`admin_cli/im.py`、`admin_cli/agents.py`

**public API surface（移除）**：`fleetent-admin`、`fleetent-node` console script 入口

**owned tables**：无　**config namespace**：无　**migration**：无

**cross-module dependencies**：无；`fleetent admin` / `fleetent node start` 分发逻辑（`__main__.py`）保持不变

**与 remove-tui-client 的关系**：两者都 MODIFY `install-bootstrap` 安装清单。remove-tui-client 当前 PARKED；本 change 先落地后，remove-tui-client 若解封需 rebase 该 spec。
