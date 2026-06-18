## ADDED Requirements

### Requirement: `fleetent admin` 子命令组

`fleetent` 命令 SHALL 支持 `admin` 子命令组，`fleetent admin <cmd>` SHALL 等价于当前 `fleetent-admin <cmd>` 的全部功能。admin 子命令的实现 SHALL 复用 `platform.admin_cli` 现有模块，不重新实现业务逻辑。

#### Scenario: admin 子命令转发

- **WHEN** 用户运行 `fleetent admin list-users`
- **THEN** 等价于运行 `fleetent-admin list-users`，输出相同

#### Scenario: admin 子命令 help

- **WHEN** 用户运行 `fleetent admin --help`
- **THEN** 显示所有可用 admin 子命令列表

### Requirement: `fleetent node start` 子命令

`fleetent` 命令 SHALL 支持 `node start` 子命令，`fleetent node start` SHALL 启动 node supervisor，等价于当前 `fleetent-node`。

#### Scenario: node start 启动 supervisor

- **WHEN** 用户运行 `fleetent node start`
- **THEN** node supervisor 进程启动，行为与 `fleetent-node` 相同

### Requirement: `fleetent-admin` deprecation shim

`fleetent-admin` 脚本 SHALL 保持可用（`pyproject.toml` 保留入口），但调用时 SHALL 打印 deprecation 警告后将命令转发给 `fleetent admin`，不改变命令执行结果。

#### Scenario: 旧命令打印警告并成功执行

- **WHEN** 用户运行 `fleetent-admin create-user --name Alice`
- **THEN** stderr 打印 `DeprecationWarning: fleetent-admin is deprecated; use: fleetent admin create-user`
- **AND** 命令正常执行，用户 Alice 被创建

### Requirement: `fleetent-node` deprecation shim

`fleetent-node` 脚本 SHALL 保持可用，但调用时 SHALL 打印 deprecation 警告后将命令转发给 `fleetent node start`。

#### Scenario: 旧命令打印警告并启动 supervisor

- **WHEN** 用户运行 `fleetent-node`
- **THEN** stderr 打印 deprecation 警告
- **AND** node supervisor 正常启动

### Requirement: agent runtime 启动路径不加载 admin 代码

`fleetent agent run <id>` 启动时 SHALL NOT 导入 `platform.admin_cli` 或其他 platform 模块；admin 子命令的 import SHALL 延迟到进入 `admin` 分支时执行。

#### Scenario: agent run 不触发 platform 导入

- **WHEN** `fleetent agent run support` 启动
- **THEN** `sys.modules` 中不含 `fleetent.platform.admin_cli`

## REMOVED Requirements

### Requirement: B 类冗余 CLI 命令

**Reason**: 以下命令已有等价 HTTP API（由 `add-platform-admin-apis` 提供），CLI 入口冗余。

**Migration**:
- 用户/Agent/KB 管理 → 使用平台 HTTP API（`/admin/users/*`、`/admin/agents/*`、`/admin/kb/connectors/*`）
- 可观测数据 → 使用 `/admin/stats/*` API

已移除命令：`create-user`、`list-users`、`rotate-key`、`block-user`、`update-agent`、`list-agent-versions`、`activate-agent-version`、`show-agent`、`assign-user`、`unassign-user`、`set-default-agent`、`kb connectors list`、`kb connectors check`、`kb connectors status`、`kb connectors sync`、`observability traces`、`observability usage`、`observability performance`。

#### Scenario: 已移除命令不再可用

- **WHEN** 用户运行 `fleetent admin create-user`（或其他已移除命令）
- **THEN** 命令不存在，argparse 报 `invalid choice` 错误，提示使用 HTTP API
