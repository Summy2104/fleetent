# 平台数据完整性与门控收尾

## Why

平台侧表结构重构审计(对当前 main head 复核确认)留下一批**互不重叠、基本无需产品决策**的完整性缺口与一处安全门控缺失,各自小、风险低,适合一次内聚清理一并收掉:

- 归档保护 `references()` 只查 `user_agents`(`channels` 恒空)→ 绑了 KB/MCP/skill/grant/placement 但没绑 user 的 agent 可被静默归档,保护形同虚设。
- `node_agent_status`(node 上报的运行态投影)没有删除路径 → unpin/deregister 后留下"幽灵 running 行",控制台运行态视图与真实期望态长期失同步。
- 死函数 `get_agent_for_user()` 全仓零调用。
- `external_services.enabled=false` 完全无门控 → 管理员以为禁用了某外部服务,实则仍可被工具 OAuth 凭证链授权/使用(安全缺口)。
- `teams` 缺 `UNIQUE(id, tenant_id)`、`agents.team_id` 仅单列 FK → 租户 A 的 agent 可引用租户 B 的 team(违反数据主权强隔离);`api_keys.user_id` 无 FK → 删用户不级联,产生可能仍可认证的孤儿 key。

## What Changes

- **归档引用保护补全**:`references()` 纳入 `agent_im_groups` / `agent_mcp_servers` / `agent_kbs` / `agent_service_grants` / `agent_placements`,保留"有引用即阻断归档"的现有语义(不降级为 warn)。
- **node 上报态清理**:`unpin_agent` 与 `deregister_node` 同步 `DELETE FROM node_agent_status`(按 agent_id / node_id),消除幽灵 running 行。
- **删死函数**:移除 `get_agent_for_user()` 及其测试引用。
- **禁用即门控**:工具 OAuth 凭证解析链对 `external_services.enabled=false` 的服务拒绝解析/使用(等价"未授权")。属行为变更,语义显然。
- **BREAKING(DB schema)— 租户 FK 完整性**:`teams` 加 `UNIQUE(id, tenant_id)`;`agents.team_id` 升级为复合外键 `(team_id, tenant_id) → teams(id, tenant_id)`;`api_keys.user_id` 补 `FK → users(id) ON DELETE CASCADE`。迁移**先扫存量脏数据**(跨租户 team 引用 / 孤儿 key),有脏数据先清理或显式报错。

## Capabilities

### New Capabilities

（无——本 change 全部是对既有 capability 的完整性收窄/补强。）

### Modified Capabilities

- `agent-lifecycle-toggle`:归档前的绑定保护覆盖全部引用类型(KB/MCP/skill/grant/placement/IM group),而非仅 user 绑定。
- `node-supervisor`:node 上报运行态在 unpin/deregister 时被清理,不留幽灵记录。
- `external-credential-vault`:被禁用(`enabled=false`)的外部服务在凭证解析链被门控,拒绝授权/使用。
- `tenancy-entities`:`agents.team_id` 经复合外键强制 team 与 agent 同租户(DB 级数据主权完整性)。
- `api-key-management`:`api_keys.user_id` 经外键约束,用户删除级联清理其 key,杜绝孤儿。

## Impact

### 模块边界影响声明

- **owning packages**:`platform/agent_management_console`、`platform/node_management`、`platform/connector_management`、`platform/tenancy`、平台 api_key store。
- **owned tables（仅 P3 动 schema）**:
  - `teams` — ADD `UNIQUE(id, tenant_id)`。
  - `agents` — `team_id` 重建为复合 FK `(team_id, tenant_id) → teams(id, tenant_id)`(batch 重建)。
  - `api_keys` — ADD `FK(user_id) → users(id) ON DELETE CASCADE`(batch 重建)。
  - P1/P2 **零 DDL**。
- **public API surface**:无新增/移除端点(归档保护与凭证门控均为内部行为变更)。
- **config namespace**:无。
- **cross-module dependencies**:`references()` 在 `agent_admin_store`、由 `agent_console_api.references_for` 消费;`node_agent_status` 清理在 `placement_store`/`node_store`;enabled 门控在 `connector_management/vault_provider`。
- **migration / shim plan**:单条 Alembic forward 迁移(head 105 → 106):①脏数据预扫(跨租户 team 引用 / 孤儿 api_keys)②`teams` 加 UNIQUE ③`agents` 复合 FK 重建 ④`api_keys` FK 重建。均 batch、可逆;无 shim。

### 提交纪律

P1 / P2 / P3 三组**分开 commit**,守"一次 commit 不混不相关改动";每个实现 task 前先写测试见红。P3 的脏数据预扫为该组首个 task。

### Out of Scope

- A 的 status 运行时强制(kill vs 最终一致,需决策)。
- 死列 `model_providers.temperature` / `skills.immutable_fields` / `backflow_proposals.overridden_head`(各带 remove-vs-wire 小决策;`immutable_fields` 属 skills 治理)。
- D `kb_ingest_jobs` worker 托管;G `session_meta` / skills 治理列 接or删;B1/B2/B3 UI 重设计;`agent_service_grants` 命名。
