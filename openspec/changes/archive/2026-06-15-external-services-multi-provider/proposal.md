## Why

P0 只验证「一个服务」端到端。要真正支撑 google-drive / github / confluence 等多个外部服务，需要一层 **provider 适配**：把各服务在 OAuth 授权 URL 构造、token 交换字段、client 构造、scope 表达上的差异，收敛到一个可插拔适配接口，使新增一个服务**只需注册 + 适配，不改 dispatch / consent 核心**。本变更建立该适配层并以多于一个的真实服务验证。

> Apply 顺序：依赖 `external-credential-vault`（P0）；OAuth 多服务还依赖 `oauth-token-lifecycle`（P2）的刷新对多 provider 生效。

## What Changes

- **provider 适配接口**：定义 `ServiceProvider` 适配（授权 URL 构造、code→token 交换、token→client 构造、scope 规范化），按 `service_id` 选型（工厂 key）。
- **多服务注册**：consent 流与 Vault provider 经适配层支持 ≥2 个真实服务（如 google-drive + github），新增服务不改核心代码。
- **适配层不持密钥**：`client_secret` 仍走 env；适配只处理协议形态差异。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `external-credential-vault`: 新增 provider 适配层要求——consent 与凭证解析经按 `service_id` 选型的适配接口完成，支持多服务（ADDED 扩展）。

## Impact

- **owning package**：`platform/connector_management`（`ServiceProvider` 适配接口 + 各服务适配实现 + 工厂按 `service_id` 选型）。
- **public API surface**：新增 `ServiceProvider` 适配接口与工厂；consent / Vault provider 内部经适配层——对外 `get_credential` 契约不变。
- **owned tables**：无新增（`external_services` 无 `kind` 列；工厂 key 改用已存在的 `service_id`——re-baseline 发现，无需迁移）。
- **config namespace**：无（各服务 endpoint/client_id 落 `external_services`；secret 走 env）。
- **cross-module dependencies**：纯 platform；不被 agent runtime import；外部 HTTP 测试用 respx。
- **migration / shim plan**：无 schema 迁移。
- **不在范围**：把 KB connector / MCP server 收编进该适配层（各属独立域，另议）；为每个具体云服务穷举实现（本变更建层 + ≥2 服务验证，其余按需增量加适配）。
