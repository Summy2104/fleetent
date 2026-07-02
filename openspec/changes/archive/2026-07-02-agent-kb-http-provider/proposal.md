## Why

目标拓扑下 agent node 是多机的、KB 是单机中心服务（见 [[kb-service-multi-tenant]] / Change C）。远程 agent **读不了本地 KB 文件**（in-process `LocalKnowledgeProvider` 只在 KB 与 agent 同机时成立）——必须经 **kb-serve HTTP** 读中心 KB。但现在 managed agent 默认走 `LocalKnowledgeProvider`（本地 in-process），这在 agent 与 KB 分机时**读不到 KB**。

本 change（收口程序 **D**）让 **managed（node 托管）agent 默认经 `HttpKnowledgeProvider` 读中心 kb-serve**，node 注入 kb-serve URL + 共享 service key。这**消掉两个老硬伤**：`distributed-deploy-colocation`（agent 不再需要本地 KB 副本）与 `kb-ro-mount-wal-hazard`（不再文件级挂 kb.db，无滞后快照）。

**前置**：gated on Change C（多租户 kb-serve 单端点 + 共享 service-key）落地——apply 时须对 C 的落地实现校验注入的 URL/鉴权形状。standalone dev（`fleetent agent run`，与 KB 同机）保持 `local`，无需 HTTP。

## What Changes

- **managed agent 默认 http provider**：node 托管拉起 agent 时，若未显式声明 `knowledge.provider`，SHALL 注入 `HttpKnowledgeProvider` 指向中心 kb-serve（URL + 共享 service key `auth_ref`，由 node 从其 node 配置/平台下发获知）。agent 检索请求携带自身 `principal`（tenant），由多租户 kb-serve 路由。
- **standalone 保持 local**：`fleetent agent run`（dev/test，与 KB 同机）默认仍 `LocalKnowledgeProvider`（in-process 读本地）；显式 `provider.type=http` 时走 HTTP（现状不变）。
- provider 熔断（`provider_failure_threshold` 等）复用现有机制。
- 复用现成 `HttpKnowledgeProvider`（`long_term_ctx`）与 `AgentKnowledgeProvider`（`agent_config`，已支持 type=http/url/auth_ref）——本 change 主要是 **managed 下的默认选择 + URL/key 注入接线**，非新造 provider。

**不做**：kb-serve/worker 多租户化本身（Change C）；平台退客户端（Change B）；改 provider 协议/检索语义。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `agent-knowledge-config`：`Agent knowledge provider selection` 扩展——**managed（node 托管）部署默认经 HttpKnowledgeProvider 指向中心 kb-serve**（node 注入 URL + 共享 service key），standalone（同机）保持 local 默认；agent 检索携 principal 由多租户 kb-serve 路由。

## Impact

- **代码**：`node/`（托管拉起 agent 时注入 kb-serve URL/auth 到 agent 的 knowledge.provider）；`runtime/agent_app`（managed 默认 provider 选择）；`long_term_ctx`（provider 装配，若需）；`agent_config`（provider 默认/校验，若需）。
- **不改**：kb-serve/worker（C）；平台 `/admin/kb`（B）；provider 协议。
- **spec**：`agent-knowledge-config` delta。
- **无迁移、无 schema、无 wire 破坏**（HttpKnowledgeProvider/config 已在）。
- 依赖：**gated on Change C**；与 Change B（平台侧）**无文件重叠，可并行**。
