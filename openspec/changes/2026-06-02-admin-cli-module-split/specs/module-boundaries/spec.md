## ADDED Requirements

### Requirement: Admin CLI package split
系统 SHALL 将 admin CLI 实现迁入 `platform.admin_cli` package，同时保持现有 `fleetent-admin` 入口兼容。

#### Scenario: New admin CLI package entrypoint exists
- **WHEN** 调用方导入 `fleetent.platform.admin_cli.main.main`
- **THEN** 导入成功

#### Scenario: Legacy admin entrypoint remains compatible
- **WHEN** 调用方导入 `fleetent.admin.main`
- **THEN** 导入成功
- **AND** 行为等价于新的 `fleetent.platform.admin_cli.main.main`

#### Scenario: Console script remains unchanged
- **WHEN** 查看 `pyproject.toml`
- **THEN** `fleetent-admin` 仍指向 `fleetent.admin:main`

#### Scenario: Admin shim does not contain business logic
- **WHEN** 查看 `src/fleetent/admin.py`
- **THEN** 文件只 re-export admin CLI entrypoint
- **AND** 不包含命令业务处理逻辑

### Requirement: Admin CLI command domains
admin CLI SHALL 按命令域拆分实现文件，降低单文件冲突。

#### Scenario: User and IM commands are split
- **WHEN** 查看 `platform.admin_cli`
- **THEN** user commands 和 IM commands 分别位于独立模块

#### Scenario: Pilot operations commands are split
- **WHEN** 查看 `platform.admin_cli`
- **THEN** KB connector、diagnostics 和 observability commands 分别位于独立模块

#### Scenario: Existing admin CLI behavior is preserved
- **WHEN** 运行现有 admin CLI integration tests
- **THEN** 用户、IM、agent/channel、schedule、KB connector、diagnostics 和 observability 命令行为保持不变

#### Scenario: Command modules expose a small registration contract
- **WHEN** 查看 `platform.admin_cli` 的命令域模块
- **THEN** 每个模块通过 `register(subparsers)` 注册自身命令
- **AND** 通过 `handle(args)` 处理自身命令并返回是否已处理
