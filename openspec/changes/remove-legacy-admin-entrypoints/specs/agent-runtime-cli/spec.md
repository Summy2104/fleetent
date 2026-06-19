## ADDED Requirements

### Requirement: `fleetent admin` 子命令组

`fleetent` 命令 SHALL 提供 `admin` 子命令组，作为平台管理 CLI 的**唯一**入口（旧 `fleetent-admin` console script 已移除）。`fleetent admin <cmd>` SHALL 复用 `platform.admin_cli` 实现；`fleetent admin --help` 的 usage 行 SHALL 显示 `fleetent admin`。admin 子命令的 import SHALL 懒加载，不在 `fleetent agent run` 启动路径触发。

#### Scenario: admin 子命令可用

- **WHEN** 用户运行 `fleetent admin list-tenants`（保留命令）
- **THEN** 命令执行，输出与底层 `platform.admin_cli` 实现一致

#### Scenario: 旧 fleetent-admin 入口不再存在

- **WHEN** 查看 `pyproject.toml` 的 `[project.scripts]`
- **THEN** 不含 `fleetent-admin` 入口；管理 CLI 仅经 `fleetent admin` 暴露

#### Scenario: agent run 不加载 admin 代码

- **WHEN** 调度到 `fleetent agent run` 分支（serve 被 mock，sys.modules 先清除 `fleetent.platform.admin_cli`）
- **THEN** `fleetent.platform.admin_cli` 不在 `sys.modules`

### Requirement: `fleetent node start` 子命令

`fleetent` 命令 SHALL 提供 `node start`，启动 node supervisor，作为其**唯一**入口（旧 `fleetent-node` console script 已移除）。node 配置经 `FLEETENT_NODE_*` 环境变量，无命令行参数透传。

#### Scenario: node start 启动 supervisor

- **WHEN** 用户运行 `fleetent node start`
- **THEN** node supervisor 启动，行为与旧 `fleetent-node` 相同

#### Scenario: 旧 fleetent-node 入口不再存在

- **WHEN** 查看 `pyproject.toml` 的 `[project.scripts]`
- **THEN** 不含 `fleetent-node` 入口；node supervisor 仅经 `fleetent node start` 启动
