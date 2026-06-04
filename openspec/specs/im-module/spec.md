# im-module Specification

## Purpose
统一 IM 模块（`platform/im_gateway_management`）将 IM 身份映射、用户 allowlist、connector
配置/凭证、connector registry/status、connector manager 与 `/admin/im` admin router 合并为
单一模块边界，对外只暴露一个 public API surface。

## Requirements
### Requirement: Unified IM module public API

系统 SHALL 提供单一 IM 模块，统一暴露 IM 身份映射、用户 allowlist、connector
配置/凭证、connector registry/status、connector manager 以及 `/admin/im` admin
router。跨模块调用方 MUST 通过该模块的 public API surface 调用，MUST NOT import 其
内部实现文件。

#### Scenario: 入站消息解析使用统一 IM 模块

- **WHEN** IM gateway 处理一条入站消息，需要把 `(owner_id, platform, platform_user_id)`
  映射到内部用户并检查 allowlist
- **THEN** 它通过统一 IM 模块的 public API 完成映射与 allowlist 检查，而不是分别 import
  两个独立模块

#### Scenario: connector 凭证解析与身份映射来自同一模块

- **WHEN** 调用方需要解析某 owner/platform 的 connector 凭证以及该 platform 的用户身份
- **THEN** 两者都从统一 IM 模块的 public API 获得

### Requirement: IM module owns all IM tables

统一 IM 模块 SHALL 是 `im_users`、`im_connectors`、`im_channel_allowlist` 三张表的唯一
owner module，负责其 store 访问与 public DTO。其他模块 MUST NOT 直接 query 或 mutate
这些表。

#### Scenario: 其他模块访问 IM 数据

- **WHEN** governance blocklist 需要封禁某 IM 身份
- **THEN** 它通过统一 IM 模块 public API 操作，而不是直接对 `im_users` 发 SQL

### Requirement: Legacy IM import paths are compatibility shims

旧 IM import 路径 SHALL 保留为 compatibility shim，仅 re-export 统一 IM 模块的 public
names，MUST NOT 包含业务逻辑。受影响路径为 `fleetent.im_user_store` 及
`fleetent.platform.im_gateway_management` 下的 `im_connector_store`、
`im_connector_config`、`im_connector_manager`、`im_channel_allowlist`、`im_admin_api`。

#### Scenario: 旧路径 import 仍可用

- **WHEN** 既有代码或测试从旧 import 路径导入 IM 名称
- **THEN** 导入成功并解析到统一 IM 模块的同一实现对象

#### Scenario: shim 不承载业务逻辑

- **WHEN** 查看任一 IM compatibility shim 文件
- **THEN** 该文件只做 re-export，新增/修改的 IM 业务逻辑位于统一 IM 模块中

### Requirement: Behavior-preserving consolidation

合并 SHALL 不改变 IM 行为：三张表的列、键与既有 legacy-rebuild/`_init_db` 行为不变，
`/admin/im/*` 路由路径不变，connector 凭证 masking 与 admin-only 鉴权不变，不引入
Alembic migration。

#### Scenario: admin IM 路由路径不变

- **WHEN** admin console 调用 `/admin/im/connectors` 及其它 `/admin/im/*` 端点
- **THEN** 路径与响应语义与合并前一致

#### Scenario: 凭证读取仍 masked 且 admin-only

- **WHEN** 非 admin 读取 connector 配置，或任意人读取 connector 凭证
- **THEN** 非 admin 被拒绝；凭证值按合并前规则 masked
