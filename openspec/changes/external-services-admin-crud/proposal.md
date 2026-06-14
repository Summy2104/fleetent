## Why

`external-credential-vault`（P0）落地了单层全局的 `external_services` 注册表与 `agent_service_grants` 授权表，但 P0 切片只打通「一个服务、一个工具」的端到端，**管理面尚未让管理员完整授权**：注册多协议服务（OAuth / API key 二选一）、为 agent 绑定可用服务并指定 `run_as`。本变更补齐 external_services 与 agent_service_grants 的 admin CRUD，使「新增服务、把服务授权给 agent」无需改代码。

> Apply 顺序：依赖 `external-credential-vault`（P0）先 archive（`external_services` / `agent_service_grants` 表与 store 已就位）。

## What Changes

- **external_services 注册表 admin CRUD**：list / add / edit / delete，显式承载 `protocol`（`oauth2_authcode` | `api_key`）、`kind`、authorize/token endpoint、`client_id`、scopes、`enabled`；`client_secret` 永不返回明文。
- **agent_service_grants 授权 admin**：为 agent 绑定 / 解绑可用服务，并设置 `run_as`（`user` | `agent`）；列出某 agent 已授权服务、某服务已授权 agent。
- 仅 admin 可写，viewer 只读（403 守卫）。所有写操作落审计。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `oauth-connector-admin`: 「Connector directory and configuration」目录项新增 `protocol` 维度（OAuth / API key），并明确目录为单层全局（无 owning-agent 列，承接 P0 移除的覆盖层）。
- `agent-oauth-binding`: 新增 admin 授权语义——管理员可经 admin 面 bind/unbind 服务并设置 `run_as`（store 在 P0 已就位，此处补「可经 admin 写入与读取」的要求）。

## Impact

- **owning package**：`platform/connector_management`（`external_services` store + `agent_service_grants` store 的 admin 端点）、`platform/agent_management_console`（agent 侧服务绑定端点，复用 P0 store）。
- **public API surface**：admin 端点 `/admin/connectors`（CRUD，含 protocol）、`/admin/agents/{name}/bindings/oauth`（bind/unbind + run_as）；store 函数沿用 P0 命名。
- **owned tables**：无新增（沿用 `external_services` / `agent_service_grants`）。
- **config namespace**：无。
- **cross-module dependencies**：纯 platform 管理面；不被 agent runtime import；不碰 agent⊥platform。
- **migration / shim plan**：无 schema 迁移（P0 已建表）；旧 `connector_config_store` / `agent_oauth_binding_store` import 路径的 re-export shim 由 P0 提供，本变更沿用。
- **不在范围**：grants 矩阵 / revoke / offboarding / lifecycle（P5）、token 生命周期（P2）、API-key 用户提交流（P3）。
