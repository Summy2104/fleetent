## Why

P0 把 `connectors`→`external_services`、`agent_oauth_bindings`→`agent_service_grants` 改名并移除 `connectors.agent_id` 休眠列，运行时经 re-export shim 不破，但**主 specs 与 `data-model.md` 仍写旧表名**。本变更做一次性文案对账，消除规格漂移，使主 specs 与实现一致。仅改文案/表名引用，不改任何运行时行为。

> Apply 顺序：在 P0 之后（建议待 P0–P6 落定后统一对账，作为收口）。

## What Changes

- **`agent-definition`**：`agent_oauth_bindings`→`agent_service_grants`（删除级联清单 + FK CASCADE 覆盖清单）；`connectors.agent_id` 休眠列相关需求/场景更新为「已随 `connectors`→`external_services` 移除」。
- **`agent-admin-api`**：agent 侧 OAuth 绑定端点描述中「connector catalog / connector」实体术语对账为「external services / service」；**HTTP 端点路径与路径参数 token 保持不变**（向后兼容）。
- **`oauth-mcp-admin-ui`**：OAuth Connectors tab 的「connector configs / catalog」实体术语对账为 external services registry；端点路径不变。
- **`docs/architecture/data-model.md`**：表名、ER 边、phantom-edge 标注更新（`connectors`→`external_services` 去 agent_id 覆盖层、`agent_oauth_bindings`→`agent_service_grants` + run_as、新增 `external_credentials`、工具 OAuth 由「phantom/unwired」改为「已接线 per-principal vault」）。
- **明确剔除**：`configuration` spec 里的 `connectors.*`/`*_env` 指 **agent.yaml 的 IM 凭证引用**（IM 域，重载词），**不属本次对账**，不动。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `agent-definition`: 删除级联与 FK 覆盖清单中的 `agent_oauth_bindings` 改名、`connectors.agent_id` 休眠列需求更新。
- `agent-admin-api`: OAuth 绑定端点实体术语对账（路径不变）。
- `oauth-mcp-admin-ui`: OAuth Connectors tab 实体术语对账（路径不变）。

## Impact

- **owning package**：无代码行为变更——仅 spec 文案 + `data-model.md`。若有 store/变量名中 `connector_id`→`service_id` 的内部术语统一，属可选清理，不改 API 路径。
- **public API surface**：不变（HTTP 端点路径与路径参数 token 保持，向后兼容）。
- **owned tables**：不变（P0 已改名建表）。
- **config namespace**：不变。
- **cross-module dependencies**：无。
- **migration / shim plan**：无迁移；P0 的 re-export shim 在术语统一后可视情况收敛（非必需）。
- **不在范围**：`configuration`（IM 凭证，重载词，剔除）；MCP 命名需求里把 `connectors` 作为「命名惯例 exemplar」的旁注（如需可顺带，但不强制，避免触碰 MCP-owned 需求）。**本次唯一允许触碰 `data-model.md` 的变更**（前序 P0–P6 均不碰）。
