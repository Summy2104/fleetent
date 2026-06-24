## MODIFIED Requirements

### Requirement: Platform CLI package split

系统 SHALL expose the Platform CLI through `platform.platform_cli` canonical package
paths only; the legacy `fleetent.admin` shim SHALL NOT remain importable. The Platform
CLI SHALL be invoked exclusively via the `fleetent platform` subcommand of the single
`fleetent` entrypoint; the standalone `fleetent-admin` console script SHALL NOT exist
in `pyproject.toml`. `platform.platform_cli.main.main` SHALL remain importable as the
canonical implementation that `fleetent platform` delegates to.

#### Scenario: New Platform CLI package entrypoint exists
- **WHEN** 调用方导入 `fleetent.platform.platform_cli.main.main`
- **THEN** 导入成功

#### Scenario: Legacy admin entrypoint is removed
- **WHEN** 调用方导入 `fleetent.admin`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: No standalone admin console script
- **WHEN** 查看 `pyproject.toml` 的 `[project.scripts]`
- **THEN** 不含 `fleetent-admin` 入口；Platform CLI 仅经 `fleetent platform` 子命令暴露

### Requirement: Platform CLI command domains

Platform CLI SHALL 按命令域拆分实现文件，降低单文件冲突。

#### Scenario: User and IM commands are split
- **WHEN** 查看 `platform.platform_cli`
- **THEN** user commands 和 IM commands 分别位于独立模块

#### Scenario: Pilot operations commands are split
- **WHEN** 查看 `platform.platform_cli`
- **THEN** KB connector、diagnostics 和 observability commands 分别位于独立模块

#### Scenario: Existing Platform CLI behavior is preserved under new namespace
- **WHEN** 运行迁移后的 Platform CLI integration tests
- **THEN** 用户、IM、agent/channel、schedule、KB connector、diagnostics 和 observability 命令行为保持不变

#### Scenario: Command modules expose a small registration contract
- **WHEN** 查看 `platform.platform_cli` 的命令域模块
- **THEN** 每个模块通过 `register(subparsers)` 注册自身命令
- **AND** 通过 `handle(args)` 处理自身命令并返回是否已处理

### Requirement: Current docs reference canonical Platform CLI entrypoint

当前文档 SHALL 使用 `fleetent.platform.platform_cli` 或 `fleetent platform` 子命令表示
Platform CLI 入口。

#### Scenario: Current docs use Platform CLI terminology
- **WHEN** 读者查看当前 platform 或 architecture docs
- **THEN** 文档使用 `fleetent.platform.platform_cli` 或 `fleetent platform` 子命令表示 Platform CLI 入口
- **AND** 不把 `fleetent.admin`、`fleetent admin` 或已移除的 `fleetent-admin` console script 描述为当前实现入口

#### Scenario: Deleted legacy paths are not described as current APIs
- **WHEN** 当前 docs 描述 memory、governance、integrations 或 Platform CLI
- **THEN** 文档不把已删除 legacy import path 描述为仍可用 public API

#### Scenario: Historical archive docs remain historical
- **WHEN** 搜索 `docs/archive/**` 或 `openspec/changes/archive/**`
- **THEN** 历史记录可以保留 legacy 模块名
- **AND** 本 change 不要求重写历史设计记录

### Requirement: Platform CLI 直写管理库的边界

`fleetent platform` CLI 直接访问管理面 store（不经平台 HTTP server 写管理库）SHALL
仅限以下三类：

- **真 bootstrap**：必须在 server 起来之前/之外运行的操作（如 `seed-builtin-admin` 创建首个内置 admin、`init-config`、`validate-config`）。
- **基础设施供给**：`agent-node-registry` spec 已界定为"先于/独立于平台业务管理"的 ops 入口（node 登记/列举/注销/pin/unpin）。
- **危险宿主级维护**：在平台宿主上人工执行的低频危险操作（`diagnostics`、`maintenance`）。

业务控制面操作——租户/团队创建、用户归属（`tenant_id`）设置、审批人（`approver_user_id`）配置及同类——MUST 经平台 HTTP API 执行，MUST NOT 提供绕过 server（直写管理库、跳过 session 鉴权与 HTTP 审计）的 CLI 路径。判据是"该操作是否必须在 server 之前/之外运行"，而非"是否已有 HTTP 等价"。

#### Scenario: 业务控制面操作无直写 CLI

- **WHEN** 查看 `fleetent platform` 子命令集合
- **THEN** 不存在 `create-tenant` / `list-tenants` / `create-team` / `set-user-tenant` / `set-approver` 等直写管理库的租户管理命令
- **AND** 这些操作仅经 `/admin/tenancy/*` HTTP API 提供

#### Scenario: bootstrap 与基础设施供给可直写

- **WHEN** 运维执行 `fleetent platform seed-builtin-admin` 或 `fleetent platform node register`
- **THEN** 允许直接写管理库——前者是 server 起来前的 bootstrap，后者是 spec 认可的基础设施供给入口

#### Scenario: 新增业务控制面操作走 HTTP

- **WHEN** 后续新增任一业务控制面写操作（管理库业务实体的增删改）
- **THEN** 它经平台 HTTP API 暴露，而不是新增直写管理库的 Platform CLI 命令
