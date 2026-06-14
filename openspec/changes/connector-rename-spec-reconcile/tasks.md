# Tasks — connector-rename-spec-reconcile（P7）

> 纯文案/表名对账，无运行时行为变更。建议作为收口在 P0–P6 后 apply。无 TDD 红绿（无实现代码），以 spec 校验与文档一致性为准。

## 1. 主 specs 对账

- [ ] 1.1 `agent-definition`：`agent_oauth_bindings`→`agent_service_grants`（删除级联 + FK 覆盖清单 + 场景）；`connectors.agent_id` 休眠列需求/场景改为「随 connectors→external_services 移除」。
- [ ] 1.2 `agent-admin-api`：OAuth 绑定端点实体术语 connector→external service（HTTP 路径与 token 不变）。
- [ ] 1.3 `oauth-mcp-admin-ui`：OAuth Connectors tab 实体术语 connector configs→external services registry（路径不变）。
- [ ] 1.4 `openspec validate` 三个 delta 通过。

## 2. data-model.md 对账

- [ ] 2.1 `connectors`→`external_services`（去 agent_id 列与两 partial 索引）、`agent_oauth_bindings`→`agent_service_grants`（+run_as）、新增 `external_credentials`。
- [ ] 2.2 ER 边修正：工具 OAuth 由「phantom/unwired」改为「已接线 per-principal vault」；移除 `connectors.agent_id` 相关 phantom 标注。

## 3. 剔除项核验（防误伤）

- [ ] 3.1 确认 `configuration` spec 的 `connectors.*`/`*_env`（agent.yaml IM 凭证引用）**未被改动**（重载词，属 IM 域）。
- [ ] 3.2 （可选）MCP 命名需求里把 `connectors` 作为「命名惯例 exemplar」的旁注更新为 `external_services`；如触碰 MCP-owned 需求风险则跳过并记录。

## 4. shim 收敛（可选）

- [ ] 4.1 术语统一后，评估 P0 的 `connector_config_store` / `agent_oauth_binding_store` re-export shim 是否可收敛（非必需，保留亦可）。
