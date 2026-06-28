# 退役 agent 版本化与 askit,确立 agents 为单一真相源

## Why

askit/spec-driven 部署器已退役,agent 现在全部由控制台手捏(adhoc)。当年为 askit 建的整套机器——agent 配置版本化(`agent_versions`)、声明式 `apply` API、`provenance`(managed/adhoc)、agent 级 `drift` 汇总——失去了驱动者,沦为死重;其中"配置版本化"还是半成品且**会误导用户**:激活旧版本只回滚 6 个运行时字段,而 features/plugins/config_overrides 等留在 `agents` 表不随版本走,"回滚"是个半身回滚,前端又不展示版本 diff。

已决定 v1 **不需要配置回滚能力**(未来若需要,可在 agents 单一真相源之上纯加法迭代:append-only 快照表 + restore,不必先回退本次改动)。本次把这套死重退役,确立 `agents` 表为 agent 配置的**唯一当前态真相源**,并顺带把 MCP 挂载的"多处表示"收敛为单一关系表。

四条退役前提已逐条对照 head-104 代码核实(apply 无任何调用方 / 只有 apply 标 managed / agent 级 drift 与 skill backflow 数据分离可外科切除 / `active_version_id` 无版本机器之外的消费方),全部成立。

## What Changes

- **agents 单一真相源**:把 `model_overrides`、`memory_namespace`、`skills_dir` 从 `agent_versions` 搬进 `agents` 表;`agents.system_prompt`/`allowed_tools`(现为写后即死的副本)转正为活权威。所有读点(materialize、`credential_slots` 的两处 JOIN、控制台投影、`agent_store.get_by_name/get_by_id`)改为直接读 `agents`。
- **BREAKING — 移除配置版本化**:DROP `agent_versions` 表与 `agents.active_version_id` 列;删除 `create_version`/`activate_version`/`list_versions`/`get_version_by_id` 等;移除 `GET /admin/agents/{name}/versions`、`POST .../versions/{version}/activate` 两端点及前端版本历史 UI。
- **BREAKING — 退役 askit/apply**:移除 `POST /admin/agents/apply`、`apply:batch` 端点、`askit_console/agent_apply_api` 模块及 server 中 `_apply_create`/`_apply_update` seam(askit 已死、前端零调用、无内部调用方)。
- **移除 provenance**:DROP `agent_admin_state.provenance` 列(唯一的 managed-setter 是 apply,退役后恒为 adhoc);清理控制台投影字段、前端 provenance badge、stats 的 provenance 统计。
- **外科移除 agent 级 drift 汇总**:DROP `agent_admin_state.drift` 列;仅删除 `node_desired_state_api` 中 `any_drift → mark_drift/clear_drift` 的汇总段、控制台 edit 的 `mark_drift` 调用、`mark_drift`/`clear_drift` 函数及前端 drift badge。**保留** per-skill 的 `agent_skills.drift` / `skill_admin_store.set_drift` / `backflow_store.nominate`——那是独立运转的 skill backflow 活功能,不得触碰。
- **MCP 挂载收敛单一真相源**:`agent_versions` 删除后 `mcp_server_ids` JSON 表示随之消失,`agent_mcp_servers` 关系表成为 MCP 挂载唯一真相源(materialize 不再合并两源)。

## Capabilities

### New Capabilities

- `agent-config-single-source`:agent 配置以当前态形式存于 `agents` 表,无版本化、无回滚;定义所有运行时配置字段的唯一存放与读取契约。

### Modified Capabilities

- `agent-versioning`:**整体移除**——退役配置版本化与 `active_version_id` 指针机制。
- `fleetent-apply-api`:**整体移除**——退役声明式 apply / apply:batch 入口。
- `fleetent-self-managed-provenance`:**整体移除**——apply 驱动的 managed 收编(adhoc→managed adopt)随 apply 退役。
- `agent-provenance`:**整体移除**——退役 managed/adhoc provenance。
- `agent-mcp-binding`:收敛为 `agent_mcp_servers` 单一真相源,移除版本 JSON 表示路径。
- `platform-agent-lifecycle`:agent 生命周期收窄为 status(enable/disable/archive)+ is_default,移除 provenance 与 drift 两维。
- `agent-admin-api`:移除版本与 apply 相关端点。
- `agent-admin-ui`:移除版本历史 UI、provenance/drift badge。
- `agent-stats-aggregation`:移除 provenance 维度统计。

## Impact

### 模块边界影响声明

- **owning package**:`platform/agent_management_console`、`platform/agent_lifecycle`。
- **owned tables**:
  - `agents` — ADD `model_overrides` / `memory_namespace` / `skills_dir` 列;`system_prompt`/`allowed_tools` 转正为活权威;DROP `active_version_id`。
  - DROP `agent_versions`(整表)。
  - `agent_admin_state` — DROP `provenance`、`drift` 两列。
- **public API surface(移除)**:`POST /admin/agents/apply`、`POST /admin/agents/apply:batch`、`GET /admin/agents/{name}/versions`、`POST /admin/agents/{name}/versions/{version}/activate`。
- **config namespace**:无。
- **cross-module dependencies(触点)**:
  - `node_desired_state_api` — 外科删除 agent 级 drift 汇总段,**保留 per-skill drift + backflow**。
  - `agent_lifecycle/credential_slots` — 改 JOIN 源(active 版本 → agents)。
  - `agent_lifecycle/materialize` — 配置读源改读 agents。
  - `agent_statistics/stats_store` — 删除 provenance 统计。
  - 前端 `features/agents`(版本 UI / provenance badge / drift badge)、`features/agents` 的 stats/console 投影类型。
- **migration / shim plan**:管理库 Alembic forward 迁移——给 `agents` 加列 → 从各 agent 的 active 版本 backfill 运行时字段 → DROP `agent_versions` / `active_version_id` / `provenance` / `drift`。无数据搬迁风险(单库 Alembic,backfill 在同迁移内完成)。不保留 re-export shim(端点/表整体退役)。

### 设计纪律(延续到 design.md)

把所有"修改 agent 配置"的写入收口到**单一 choke point 函数**,为未来可选的 append-only 历史/回滚保留"一行钩子"的低成本扩展点。

### Out of Scope

- 不新建任何回滚/历史功能(仅保证未来可纯加法接入)。
- 不做 B2(agent 绑定分散)与 B3(model provider/model)的 UI 重设计。
- B1 仅顺手收敛了 MCP 双权威这一半;"connector 一词多义"不在本次范围。
