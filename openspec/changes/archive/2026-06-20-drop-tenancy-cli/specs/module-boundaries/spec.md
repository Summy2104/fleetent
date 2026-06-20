## ADDED Requirements

### Requirement: Admin CLI 直写管理库的边界

`fleetent admin` CLI 直接访问管理面 store（不经平台 HTTP server 写管理库）SHALL 仅限以下三类：

- **真 bootstrap**：必须在 server 起来之前/之外运行的操作（如 `seed-builtin-admin` 创建首个内置 admin、`init-config`、`validate-config`）。
- **基础设施供给**：`agent-node-registry` spec 已界定为"先于/独立于平台业务管理"的 ops 入口（node 登记/列举/注销/pin/unpin）。
- **危险宿主级维护**：在平台宿主上人工执行的低频危险操作（`diagnostics`、`maintenance`）。

业务控制面操作——租户/团队创建、用户归属（`tenant_id`）设置、审批人（`approver_user_id`）配置及同类——MUST 经平台 HTTP API 执行，MUST NOT 提供绕过 server（直写管理库、跳过 session 鉴权与 HTTP 审计）的 CLI 路径。判据是"该操作是否必须在 server 之前/之外运行"，而非"是否已有 HTTP 等价"。

#### Scenario: 业务控制面操作无直写 CLI

- **WHEN** 查看 `fleetent admin` 子命令集合
- **THEN** 不存在 `create-tenant` / `list-tenants` / `create-team` / `set-user-tenant` / `set-approver` 等直写管理库的租户管理命令
- **AND** 这些操作仅经 `/admin/tenancy/*` HTTP API 提供

#### Scenario: bootstrap 与基础设施供给可直写

- **WHEN** 运维执行 `fleetent admin seed-builtin-admin` 或 `fleetent admin node register`
- **THEN** 允许直接写管理库——前者是 server 起来前的 bootstrap，后者是 spec 认可的基础设施供给入口

#### Scenario: 新增业务控制面操作走 HTTP

- **WHEN** 后续新增任一业务控制面写操作（管理库业务实体的增删改）
- **THEN** 它经平台 HTTP API 暴露，而不是新增直写管理库的 admin CLI 命令
