## Context

工具 OAuth Vault（`external_services` / `external_credentials` / `agent_service_grants` + `vault_provider` + `/admin/connectors*` + 前端 OAuth tab）于迁移 093 落地，设计为 per-principal 凭证库。代码核实结论：**零生产工具消费**——唯一 `@tool(connector="github")` 是测试工具，前端 OAuth tab 从未在 `configure.tsx` 渲染。团队决定工具凭证鉴权挪到 agent 侧实现（非撤能力），平台退役这套半成品。

约束：
- **解耦护栏**：agent 运行时对三表零直接 import（`import fleetent.platform.*` 被护栏禁止），只经注入的 `connectors.py` seam 间接访问。删表对 agent 侧零直接影响。
- **验证基线**（AGENTS.md）：agent 必须能在"无 platform、platform DB 表不存在"环境完成 `fleetent agent run`。
- **双权威**：管理表仅由 Alembic 维护；删表走 forward-only 迁移 108。
- **并行边界**：方向二（model-registry-split）已落地 main；change ②（slim-mcp-to-agent-auth）将动 MCP。本 change 不碰 model/provider、不碰 MCP、不碰 `blocked_registrations`。

## Goals / Non-Goals

**Goals:**
- 删除 platform 侧 Vault 全栈（三表 + store + provider + API + 前端 OAuth 面 + 注入/hook）。
- 保留 agent 侧 `connectors.py` seam 与 `tools/registry.py` connector 通道，解注入后安全降级为 `NeedsConsent`。
- 保留测试工具 `github_connection_status` 作为 seam canary。
- 守住验证基线：无 platform 环境 `fleetent agent run` 仍通。

**Non-Goals:**
- 不实现 agent 侧凭证 provider（将来单独 change）。
- 不动 `agent-service-principal` 身份机制（被 user_store/agent_store 广泛消费，非 vault 专属）。
- 不动 sandbox 的 `run_as`（与 vault grant `run_as` 同名异义）。
- 不动 MCP 鉴权 / model / provider / blocklist。
- 不做绑定模型/视图统一（留干净地基后单独谈）。

## Decisions

### D1: 保留 `connectors.py` seam，仅移除 platform 注入
**选择**：seam 与 `@tool(connector=)` 通道原样保留；`server.py` 删除 `connectors.set_provider(vault_provider.get_credential)`，`_provider` 回落 `_default_provider`（恒 `NeedsConsent`）。
**理由**："挪实现非撤能力"——seam 本就是 agent 侧、可注入的设计点（docstring 自称 swappable provider seam）。删 seam 会让将来 agent 侧实现无处接入，且要改所有 `@tool(connector=)` 调用方。
**备选**：连 seam 一起删（撤能力）——被团队决策否决。

### D2: 删表迁移顺序与 FK
**选择**：迁移 108 drop 三表。`agent_service_grants` 有 `FK agent_id→agents.id ON DELETE CASCADE`；`external_credentials` / `external_services` 为软引用（无库内 FK 指向它们）。drop 顺序无硬依赖，但按 `agent_service_grants` → `external_credentials` → `external_services` 删除以符合语义层级。
**理由**：三表间无强制 FK 链（grants.service_id 是软引用 external_services），可独立 drop。
**备选**：保留表仅停用 API——拒绝，半成品死表留着持续污染模型。

### D3: 移除 delete-agent 清凭证 hook
**选择**：删除 `server.py` 注册的 delete-agent hook（原用于删 agent 时清其 service-principal 的 `external_credentials`）。
**理由**：`external_credentials` 表已删，hook 无对象可清。`delete_agent` 仍仅 `DELETE FROM agents`；`agent_service_grants` 的 CASCADE 随表 drop 一并消失，不留孤儿。
**风险点**：确认删 hook 后 `delete_agent` 路径无残留对 `external_credential_store` 的 import。

### D4: 前端 OAuth 面移除范围
**选择**：删 `features/connectors/` 的外部服务/grants 部分、`features/agents/api.ts` 的悬空 OAuth hooks（`useAgentOauthBindingsQuery` / `useBindAgentOauthMutation` / `useUnbindAgentOauthMutation`）、控制台 OAuth Connectors tab、`/connectors` 路由与 i18n。
**理由**：hooks 本就未被 `configure.tsx` 引用（悬空），删除零渲染影响。MCP 部分（同处 `features/connectors/api.ts` 的 `McpServerRecord`）**保留**——属 change ②。
**风险点**：`features/connectors/api.ts` 同文件混放 OAuth 与 MCP 类型，删除时按符号精确摘除，勿误删 MCP。

### D5: `run_as` 同名异义消歧
**选择**：仅删 vault grant 维度的 `run_as`（`agent_service_grant_store` / `agent_oauth_binding_store` / `vault_provider` / `agent_admin_api` 的 oauth 端点）。sandbox 的 `run_as`（`integrations/sandbox/`）、`agent_config.py` 的 `run_as` 不动。
**理由**：grep `run_as` 命中多处异义来源，盲删会误伤 sandbox。

## Risks / Trade-offs

- **误删 MCP（D4）** → 前端 `connectors/api.ts` 与 `oauth-mcp-admin-ui` spec 混放 OAuth/MCP；按符号精确摘除，删除后跑前端测试 + 验证 MCP servers view 仍在。
- **残留 import 致启动崩** → 删 store/provider/hook 后 grep 全仓 `external_service_store` / `external_credential_store` / `agent_service_grant_store` / `vault_provider` 确保零残留引用；跑 `server.py` 启动冒烟。
- **CI 时间炸弹/guard 测试漏改** → 退役整套能力时，相关 guard / 端点测试需同步删/改；按 memory `fleetent-ci-timebomb-tests` 教训核查 integration 层。
- **验证基线回归** → 删注入后必须有测试覆盖"无 provider → NeedsConsent 降级"，守住 `fleetent agent run` 基线。
- **误删 service-principal（D5 邻接）** → `agent-service-principal` 被 user_store/agent_store 消费，本 change 不碰；仅删 grant 触发的 `run_as=agent` 解析路径。

## Migration Plan

1. Alembic 迁移 108：drop `agent_service_grants` → `external_credentials` → `external_services`（forward-only，无 downgrade 数据恢复义务，半成品无生产数据）。
2. 删 platform store / `vault_provider` / connector OAuth API / agent oauth 端点。
3. 解除 `server.py` 注入与 delete-agent hook。
4. 删前端 OAuth 面（精确摘除，保留 MCP）。
5. 全仓 grep 残留引用归零；启动冒烟 + 前端测试 + 无-platform `agent run` 基线。
- **回滚**：迁移 108 不提供数据回滚（无生产数据）；代码回滚经 git revert 分支。

## Open Questions

- 测试工具 `github_connection_status` 保留为 canary（已决）vs 一并删除——本 change 取保留；若 reviewer 认为 canary 冗余可在 apply 期改为删除（不影响主线）。
- `data-model.md` §3.2 三表条目与图需在 archive 阶段同步删除（归 archive specs 同步，不在实现 task）。
