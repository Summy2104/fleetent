## Why

`external-credential-vault`（P0）已经在 main 落地了单层全局的 `external_services` 注册表与 `agent_service_grants` 授权表，也交付了 `external_service_store` / `agent_service_grant_store` / `external_credential_store` / Vault provider 等真实实现。但当前管理面仍停留在 legacy 兼容层：`/admin/connectors` 仍经 `connector_config_store` 以旧 `id`/`oauth_config` 语义工作、仅接受 `protocol="oauth2"`；`/admin/agents/{name}/bindings/oauth` 仍经 `agent_oauth_binding_store` 返回 `connector_ids`，没有 `run_as`。本变更补齐 external services registry 与 agent service grants 的 admin CRUD，使「新增服务、把服务授权给 agent」无需改代码，同时把管理面从 legacy shim 重接到 P0 已落地的数据模型。

> Apply 顺序：依赖 `external-credential-vault`（P0）先 archive（`external_services` / `agent_service_grants` 表与 store 已就位）。

## What Changes

- **external_services 注册表 admin CRUD**：沿用现有 `/admin/connectors` 路由，但底层切到 `external_service_store`；显式承载 `protocol`（与现有 main 一致，先用 `oauth2` | `apikey`）、`display_name`、`oauth_config`、`enabled`；目录是单层全局，不再暴露无效的 owning-agent 过滤语义；`client_secret` 永不返回明文。
- **agent_service_grants 授权 admin**：沿用现有 `/admin/agents/{name}/bindings/oauth` 路由兼容面，但底层切到 `agent_service_grant_store`；为 agent 绑定 / 解绑可用服务并设置 `run_as`（`user` | `agent`）；列出某 agent 已授权服务、某服务已授权 agent。
- 仅 admin 可写，viewer 只读（403 守卫）。所有写操作落审计。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `oauth-connector-admin`: 「Connector directory and configuration」目录项改为对齐 P0 的 external service registry：目录为单层全局（无 owning-agent 列、无按 agent 过滤），并新增 `protocol` 维度（`oauth2` / `apikey`）。
- `agent-oauth-binding`: 新增 admin 授权语义——管理员可经现有 agent 绑定端点 bind/unbind 服务并设置 `run_as`（store 在 P0 已就位，此处补「admin API 读写 grant」的要求）。

## Impact

- **owning package**：`platform/connector_management`（`external_service_store` + connector admin 端点）、`platform/agent_management_console`（agent 侧服务绑定端点）、`platform/connector_management/agent_service_grant_store.py`（P0 已落地的 grant store）。
- **public API surface**：admin 端点 `/admin/connectors`（CRUD，含 protocol 扩展，但保持现有路由兼容面）、`/admin/agents/{name}/bindings/oauth`（bind/unbind + run_as）；store 函数以 P0 已落地命名为准：`add_service/get_service/list_services/edit_service/delete_service`、`bind/unbind/list_services_for_agent/list_agents_for_service`。
- **owned tables**：无新增（沿用 `external_services` / `agent_service_grants`）。
- **config namespace**：无。
- **cross-module dependencies**：纯 platform 管理面；复用 P0 的 `external_service_store`、`agent_service_grant_store`、`secret_crypto` / `external_credential_store` 既有契约；不被 agent runtime import；不碰 agent⊥platform。
- **migration / shim plan**：无 schema 迁移（P0 已建表）；旧 `connector_config_store` / `agent_oauth_binding_store` import 路径的 re-export shim 由 P0 提供，本变更沿用。
- **不在范围**：grants 矩阵 / revoke / offboarding / lifecycle（P5）、token 生命周期（P2）、API-key 用户提交流（P3）。
