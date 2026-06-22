## ADDED Requirements

### Requirement: `fleetent admin` 子命令组

`fleetent` 命令 SHALL 支持 `admin` 子命令组，`fleetent admin <cmd>` SHALL 等价于原 `fleetent-admin <cmd>` 的全部保留功能，复用 `platform.admin_cli` 实现，不重新实现业务逻辑。`fleetent admin --help` 的 usage 行 SHALL 显示 `fleetent admin`（而非 `fleetent-admin`）。

#### Scenario: admin 子命令转发

- **WHEN** 用户运行 `fleetent admin list-keys --user-id <id>`（保留命令）
- **THEN** 等价于原 `fleetent-admin list-keys`，输出相同

#### Scenario: admin help 显示正确 prog 名

- **WHEN** 用户运行 `fleetent admin --help`
- **THEN** usage 行显示 `fleetent admin`，列出所有保留的 admin 子命令

### Requirement: `fleetent node start` 子命令

`fleetent` 命令 SHALL 支持 `node start`，启动 node supervisor，等价于原 `fleetent node start`（配置经 `FLEETENT_NODE_*` 环境变量，无命令行参数）。

#### Scenario: node start 启动 supervisor

- **WHEN** 用户运行 `fleetent node start`
- **THEN** node supervisor 启动，行为与原 `fleetent node start` 相同

#### Scenario: node 子命令缺 start 报用法错误

- **WHEN** 用户运行 `fleetent node`（无 `start`）
- **THEN** 打印用法错误，不静默启动

### Requirement: 旧入口 deprecation shim

`fleetent-admin` 与 `fleetent node start` 脚本 SHALL 保留（`pyproject.toml` 入口指向 shim），调用时 SHALL 向 **stderr** 打印迁移提示后转发到对应新命令，不改变执行结果。

#### Scenario: fleetent-admin 转发并提示

- **WHEN** 用户运行 `fleetent-admin list-keys --user-id <id>`
- **THEN** stderr 打印 `Deprecated: 'fleetent-admin' → use 'fleetent admin'.`
- **AND** 命令正常执行

#### Scenario: fleetent node start 转发并提示

- **WHEN** 用户运行 `fleetent node start`
- **THEN** stderr 打印迁移提示，node supervisor 正常启动

### Requirement: agent runtime 启动路径不加载 admin 代码

`fleetent agent run <id>` 启动 SHALL NOT 导入 `platform.admin_cli` 或其他 platform 模块；admin/node 子命令的 import SHALL 延迟到进入对应分支。

#### Scenario: agent run 不触发 platform 导入

- **WHEN** 调度到 `fleetent agent run` 分支（serve 被 mock，sys.modules 先清除 platform.admin_cli）
- **THEN** `fleetent.platform.admin_cli` 不在 `sys.modules`

## ADDED Requirements

### Requirement: B 类冗余 CLI 命令已移除

B 类冗余 CLI 命令 SHALL NOT 再通过 `fleetent admin` 暴露；运维与控制面 SHALL 改走对应 HTTP API。

**Reason**: 以下命令均已有等价 HTTP API——其中 6 条的 API 由前置 change `complete-admin-api-coverage` 补齐——CLI 入口冗余。

**Migration**:
- `create-user` → `POST /admin/service-principals`（建服务账号即发 key）
- `rotate-key` → `POST /admin/users/{user_id}/rotate-key`
- `set-default-agent` → `PUT /admin/agents/{name}/default` / `DELETE /admin/agents/default`
- `observability traces/usage/performance` → `GET /admin/observability/{traces,usage,performance}`
- `list-users` → `GET /admin/users`；`block-user`（已是 no-op stub）→ `POST /admin/im-users/{id}/block`
- `update-agent`/`list-agent-versions`/`activate-agent-version`/`show-agent` → `/admin/agents/{name}/*`
- `assign-user`/`unassign-user` → `POST|DELETE /admin/agents/{name}/bindings/users/{user_id}`
- `kb connectors list/check/status/sync` → `/admin/kb/connectors/*`

已移除（共 18 条）：`create-user`、`list-users`、`rotate-key`、`block-user`、`update-agent`、`list-agent-versions`、`activate-agent-version`、`show-agent`、`assign-user`、`unassign-user`、`set-default-agent`、`kb connectors list`、`kb connectors check`、`kb connectors status`、`kb connectors sync`、`observability traces`、`observability usage`、`observability performance`。

#### Scenario: 已移除命令不再可用

- **WHEN** 用户运行 `fleetent admin create-user`（或其他已移除命令）
- **THEN** argparse 报 `invalid choice` 错误（命令不存在）
