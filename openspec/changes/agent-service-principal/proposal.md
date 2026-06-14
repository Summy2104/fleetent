## Why

P0 把 Vault 主键统一为 `user_id`，并奠定「principal 即 User」——但 agent 以**自身身份**访问外部系统（Case 3：未来 KB 成独立服务 / MCP server，agent 像普通用户一样持有自己的凭证）尚未落地。本变更为 agent 铸造一个 **service-principal User**，使 `agent_service_grants.run_as=agent` 的工具调用解析为「该 agent 自身 principal 的凭证」，与 per-user 凭证共用同一张 `external_credentials` 表。

> Apply 顺序：依赖 `external-credential-vault`（P0）；与 P2/P3 无强耦合（run_as=agent 的凭证可走 OAuth 或 api_key，按对应 phase 能力可用性而定）。

## What Changes

- **agent service-principal 铸造**：为每个需要自身身份的 agent 关联一个 service 类型的 User 行（`users.id` 为 TEXT，沿用 `__system__` 之类非人类 principal 先例；标识形如 `agent:<agent_id>`、`role=service`）。铸造/解析由身份层提供，幂等。
- **run_as=agent 凭证解析**：dispatch 对 `run_as=agent` 的 grant，SHALL 用该 agent 的 service-principal `user_id` 向 Vault provider 解析凭证（而非调用用户）。
- **凭证统一表**：agent 自身凭证落同一张 `external_credentials`，按 `(service_principal_user_id, service_id)` 存储；consent / 提交流复用既有路径。

## Capabilities

### New Capabilities
- `agent-service-principal`: 为 agent 铸造 / 解析 service-principal User，并据 `run_as` 决定 dispatch 取调用用户还是 agent principal 的凭证。

### Modified Capabilities
- `agent-oauth-binding`: `run_as=agent` 从「字段语义已定义、解析待填充」转为「解析生效」——dispatch 据此取 agent service-principal 的凭证。

## Impact

- **owning package**：`platform/connector_management`（run_as 解析）、身份层（`user_store` 或其上的 service-principal 铸造 helper）。
- **public API surface**：身份层新增「为 agent 获取/铸造 service-principal user_id」的函数；Vault provider 解析按 run_as 选择 principal——`get_credential` 契约形状不变。
- **owned tables**：无新增（service-principal 是 `users` 表的一行；凭证落 `external_credentials`）。若需标注 service 类型，倾向复用 `users.role`（不新增列），具体见 design.md。
- **config namespace**：无。
- **cross-module dependencies**：dispatch 在 agent runtime 侧仅经 seam 取凭证；service-principal 铸造与解析在 platform/身份层；agent runtime MUST NOT 反向 import platform。
- **migration / shim plan**：无 schema 迁移（复用 `users` / `external_credentials`）；若选 `users` 加 `kind/type` 列则需迁移（design.md 中权衡，倾向不加列）。
- **不在范围**：agent service-principal 的 INBOUND 鉴权（agent 调内部服务用 `ma-` key 属另一机制，按需另议）；多 agent 共享同一外部账号（不在 Case 3 范围）。
