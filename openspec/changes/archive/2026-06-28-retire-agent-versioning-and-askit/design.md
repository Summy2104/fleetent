# 设计:退役 agent 版本化与 askit

## Context

当前 agent 配置劈在两张管理库表,且劈法自相矛盾(详见 proposal):

- `agents` 表持有 caps 类字段(features/plugins/allowed_skills/config_overrides/icon/supports_*)+ **两个写后即死的副本** `system_prompt`/`allowed_tools`。
- `agent_versions` 表持有运行时字段(system_prompt/allowed_tools/model_overrides/memory_namespace/skills_dir/mcp_server_ids),经 `agents.active_version_id` 指针被 `agent_store.get_by_name/get_by_id` 读出——它才是这些字段的**活权威**。

下游消费链(已核实):`agent_store.get_by_*` → `materialize.agent_file_from_store` → `materialize.desired_state_payload_from_agent_file` → `GET /nodes/{id}/desired-state` 的 `config`;node 经 `_config_hash(desired.config)` 比对决定是否 respawn。**desired-state payload 不含 provenance / active_version_id**,status 闸只看 `status=="enabled"`。

askit/spec-driven 部署器已退役,`apply` 入口无任何调用方(前端零调、无 CLI、无内部 caller);`provenance` 的唯一 managed-setter 是 apply;agent 级 `agent_admin_state.drift` 与 per-skill 的 `agent_skills.drift`/backflow 数据上分离。四条退役前提均已 code-truth 核实。

## Goals / Non-Goals

**Goals:**

- 把 `agents` 表确立为 agent 配置的**唯一当前态真相源**;消除死副本与"半版本化"不自洽。
- 退役 askit 时代死重:配置版本化、`apply` API、`provenance`、agent 级 `drift` 汇总。
- 收敛 MCP 挂载为 `agent_mcp_servers` 单一真相源。
- **不打扰运行中的 agent**:迁移后 desired-state 配置内容逐字节不变,node 不因本次迁移触发批量 respawn。
- 为未来可选的回滚能力预留**纯加法**扩展点(不在本次实现)。

**Non-Goals:**

- 不实现任何回滚/历史/审计快照功能(仅保证未来可加法接入)。
- 不重设计 B2(绑定分散)、B3(model provider/model)的 UI。
- 不处理 "connector 一词多义"(B1 仅顺手收敛 MCP 双权威)。
- 不改 node↔platform 的 desired-state/status 协议本身。

## Decisions

### D1. 字段归位:agents 当当前态唯一源,而非保留 agent_versions 作审计

把 `model_overrides`/`memory_namespace`/`skills_dir` 加列到 `agents` 并从 active 版本 backfill;`system_prompt`/`allowed_tools` 已在 `agents` 有列,转正为活权威(读写都走 agents)。`mcp_server_ids` **不搬**(见 D2)。随后 DROP `agent_versions` 与 `agents.active_version_id`。

- **备选**:保留 `agent_versions` 作 append-only 审计日志(不再 read-through)。**否决**:用户已决定 v1 不要历史/审计快照;留空表是又一处死 schema,违背本次"减法"目标。未来要历史时新建干净的快照表即可(D5 已留扩展点)。

### D2. MCP 挂载单一真相源 = `agent_mcp_servers`

`agent_versions` 删除后 `mcp_server_ids` JSON 自然消失;materialize 不再合并两源,改为只读 `agent_mcp_servers`(已是前端绑定 UI 的写入目标)。

- **备选**:把 `mcp_server_ids` 也搬进 agents。**否决**:会保留"JSON 列 vs 关系表"双表示;关系表已是 UI 唯一写入口,直接收敛最干净。

### D3. agent 配置写入收口到单一 choke point

新增/收敛一个 `update_agent_config(...)` 写入函数,控制台所有"改配置"路径(原 `create_version` 触发的 prompt/tools/model/memory/skills_dir 改动 + `set_config_overrides` + `set_identity` 的 caps 改动)统一经它直写 `agents`。

- **理由**:① 现状配置写入散在 `create_version`/`set_config_overrides`/`set_identity` 多处,收口后逻辑单一可审计;② 未来要加 append-only 历史,只需在该函数里挂一行"写前存快照",零侵入。
- **备选**:各端点各自直写 agents。**否决**:散开后未来加历史要满仓找写点,违背 D5 的低成本承诺。

### D4. 迁移须保持 desired-state 配置哈希稳定(硬验收)

Alembic 迁移把 active 版本的字段值**原样** backfill 进 `agents`,使迁移前后 `materialize.desired_state_payload_from_agent_file` 对同一 agent 产出**逐字节一致**的 payload。

- **验收**:迁移前后,对一组样本 agent 计算 `_config_hash(desired_state_payload(...))` 必须相等 → node reconcile 视为无变化 → **不 respawn 运行中的 agent**。
- **备选**:接受迁移后一次性批量 respawn。**否决**:批量重启是可避免的运维噪音;虽是优雅 drain+respawn、不丢数据,但无必要。

### D5. drift 外科切除,保 skill backflow

仅移除 **agent 级**汇总:`agent_admin_state.drift` 列、`mark_drift`/`clear_drift` 函数、`node_desired_state_api.py:286-290` 的 `any_drift→mark_drift/clear_drift` 汇总段、控制台 `agent_console_api.py:477` 的 `mark_drift` 调用、前端 drift badge。

**严格保留**(一行不碰):`node_desired_state_api.py:266-285` 的 per-skill 链——`skill_admin_store.set_base_version/set_base_commit/set_drift` 与 `backflow_store.nominate_if_absent`,以及 `agent_skills` 上的 drift 列。

- **验收**:删除后,node 上报含 `skill.drift=true` 时仍触发 `backflow_store.nominate_if_absent`(回归测试守住)。

### D6. 退役 apply/provenance 全量删除,不留 shim

`apply`/`apply:batch` 端点 + `askit_console/agent_apply_api` + server 的 `_apply_create`/`_apply_update` seam 整体删除;`provenance` 列 + 控制台投影字段 + 前端 badge + `stats_store` 统计整体删除。

- **理由**:均为整功能退役、零调用方;按 AGENTS.md「shim 不承载业务逻辑」,此处无业务可承载,保留死端点/死列即是本次要清的债。

## Risks / Trade-offs

- **[批量 respawn 风险]** 迁移若使 materialized 配置变化(如字段顺序、默认值差异)→ node 把所有 agent 重启一遍。→ **缓解**:D4 的哈希稳定验收;backfill 逐字段原样拷贝;迁移后跑哈希对照。
- **[误伤 skill backflow]** drift 删过界会打塌 node skill-sync/backflow。→ **缓解**:D5 的明确保留边界 + 回归测试守住 nominate 触发。
- **[credential_slots JOIN 重指]** 两处 `JOIN agents a ON a.active_version_id = av.id` 取 model_overrides,active_version_id 删除后必须改读 agents 自身列。→ **缓解**:随 D1 同步改,单测覆盖凭证槽解析。
- **[BREAKING API 移除]** 删 `apply`/`versions` 端点。→ **缓解**:已核实零调用方(前端、CLI、askit 均无);前端相关 UI 在**同一 change**内一并移除,无跨版本破窗。
- **[放弃回滚]** 控制台改坏配置无法一键还原。→ **取舍**:已决定接受(`audit_log` 仍记"谁何时改了什么");D3/D5 的 choke-point 使未来加回滚为纯加法。

## Migration Plan

管理库单库 Alembic forward 迁移(无跨库数据搬迁):

1. `ALTER TABLE agents ADD COLUMN model_overrides / memory_namespace / skills_dir`(带与 agent_versions 一致的默认值)。
2. backfill:对每个 agent,从其 `active_version_id` 指向的 `agent_versions` 行,把 model_overrides/memory_namespace/skills_dir/system_prompt/allowed_tools **原样**写入 `agents`。
3. DROP `agent_versions` 表、`agents.active_version_id`、`agent_admin_state.provenance`、`agent_admin_state.drift`。
4. 代码侧改读源(materialize/credential_slots/console 投影/agent_store)、删版本与 apply 路径、外科删 drift 汇总、前端清理——与迁移同一 change 落地。

**回滚策略**:本迁移是 forward-only 破坏性退役(DROP 表/列)。回滚 = 还原代码 + 反向迁移重建 agent_versions/列(从 agents 当前值重建一个 v1 快照);但因已确认无外部依赖且上线前窗口,优先**前向修复**而非回滚。迁移前对管理库做标准备份(沿用 `platform upgrade` 的备份路径)。

## Open Questions

- 无悬而未决的阻塞项。`agent-definition` / `agent-scoped-runtime-config` 等 spec 是否需要 delta,在 specs 阶段按"requirement 是否实际改变"判定(配置住所变更若不改变对外行为契约,则不立 delta)。
