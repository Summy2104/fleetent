## Why

平台侧"工具 OAuth Vault"（外部服务表 / 凭证表 / grant 表 + 平台注入 provider + `/admin/connectors*` + 前端 OAuth tab）是一套 **build-but-unwired 半成品**：架构、DB、API、前端 hook 全建好，但**零生产工具消费**——唯一声明 `@tool(connector=)` 的是测试工具 `github_connection_status`，前端 OAuth tab 从未渲染。团队已决定**工具凭证鉴权挪到 agent 侧实现**（非撤能力）。继续把这套死代码留在管理面，只会让"agent 接了什么"的模型与控制台持续被多义、悬空、命名错位污染。先做这一刀纯减法净化，后续的绑定模型/视图重构才能站在干净地基上。

## What Changes

- **删除管理库三表（BREAKING）**：`external_services`、`external_credentials`、`agent_service_grants`（Alembic 迁移 108，forward-only drop）。
- **删除 platform 侧实现**：平台注入 provider 及三类 legacy store。
- **删除管理 API（BREAKING）**：`/admin/connectors*`（list/add/edit/delete）、`/admin/connectors/grants` 授权矩阵、OAuth 授权 + 回调端点、`/admin/agents/{name}/bindings/oauth*`。
- **删除前端 OAuth 面**：`features/connectors/` 的外部服务/grants 部分、悬空的 agent OAuth hooks、控制台的 OAuth Connectors tab 与 `/connectors` 导航/i18n。
- **解除 platform 注入**：`server.py` 不再注入平台 provider，移除 delete-agent 清凭证 hook。
- **保留 agent 侧 seam（关键，非删除）**：`src/fleetent/connectors.py`（`get_credential` / `Credential` / `NeedsConsent` / `CredentialError` / `set_provider` / `_default_provider`）与 `tools/registry.py` 的 `@tool(connector=)` 通道**原样保留**。解除注入后 `_provider` 回落 `_default_provider`（恒 `NeedsConsent`）= **安全降级**，将来 agent 侧自行 `set_provider`。
- **保留 canary**：测试工具 `github_connection_status` 保留，撤 vault 后返回 `NeedsConsent`，证明 seam 仍在。

## Capabilities

### New Capabilities
（无——本 change 为纯减法。）

### Modified Capabilities
- `external-credential-vault`: 移除整个能力——退役 `external_services` / `external_credentials` 注册表与 OAuth consent 解析。
- `agent-oauth-binding`: 移除整个能力——退役 `agent_service_grants` 绑定 store 与 `run_as` grant。
- `oauth-connector-admin`: 移除整个能力——退役 `/admin/connectors*` 服务目录与 grants 管理 API。
- `oauth-mcp-admin-ui`: 移除 "OAuth Connectors tab" 要求；该 spec 的 MCP 管理 UI 部分**不动**（属 change ② 范围）。
- `connector-credential-injection`: 修改——明确 seam 在 vault 退役后**存续**：未注入 provider 时 `get_credential` 经 `_default_provider` 恒返回 `NeedsConsent`（安全降级，不崩），platform 不再注入 provider。

## Impact

- **Owning package**：`platform/connector_management/`（大半删空）。Touches：`server.py`（解注入 + 删 hook）、`platform/agent_management_console/agent_admin_api.py`（删 oauth 端点）、`frontend/src/features/connectors/` + `features/agents/api.ts`（删 OAuth hooks）+ nav/i18n。
- **Owned tables**：drop `external_services` / `external_credentials` / `agent_service_grants`（迁移 108）。
- **Public API（BREAKING）**：移除 `/admin/connectors*`、`/admin/connectors/grants`、`/admin/agents/{name}/bindings/oauth*`。
- **Config namespace**：无。
- **Cross-module deps**：`connectors.py` seam + `tools/registry.py` connector 通道（agent 侧）**保留不动**；agent 运行时对三表本就零直接 import（解耦护栏）。
- **明确不碰（防越界）**：`agent-service-principal`（更广的身份机制，被 user_store/agent_store 消费，非 vault 专属）；sandbox 的 `run_as`（与 vault `run_as` 同名异义）；`user-blocklist` / `blocked_registrations`（活跃功能，必须保留）；MCP 鉴权（change ② `slim-mcp-to-agent-auth`）；model/provider（方向二，已落地 main）。
- **验证基线**：agent 必须能在"无 platform、platform DB 表不存在"环境完成 `fleetent agent run`——`connectors.py` 默认 provider 的 `NeedsConsent` 降级保证此基线。
