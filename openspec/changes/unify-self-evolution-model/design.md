## Context

自进化三域(memory/skill/kb)当前 4 张表、不对称、有 spec 矛盾(详见 proposal)。决策原则:**按"是否共享行为"决定合表**——

- proposals 共享一套生命周期(状态机 + 审批/apply 审计)→ 合 1 张(否则抄三遍);域差异是不透明载荷,入 `payload_json`,apply 按域分派。
- reports 是终态只读日志、**无共享行为**;日志天然 1 张表 + `domain` 列,域差异入 `findings_json`。

结论:**2 表内核**(1 report + 1 proposal),均在 per-agent `agent_state.db`。

## Goals / Non-Goals

**Goals:**
- 收口为统一 `reflection_reports` + `reflection_proposals`(三域),退场 4 张旧表。
- 补 KB 自进化(domain=kb 提案 + v1 apply handler),落实 self-evolution-split 路由。
- 顺带修 #4(kb 报告并入统一表,不再静默丢)。

**Non-Goals:**
- KB 接线 + 图谱 lift(独立 change `wire-kb-tenant-routing`,动 kb.db)。
- 搬迁历史 pending 提案(瞬态,新表全新建)。
- KB v1 之外的提案动作(后续加 kind+handler,不改表)。

## Decisions

### D1：2 表 schema（agent_state.db · 统一 MIGRATIONS）
```
reflection_reports
  id · domain(memory|skill|knowledge_base) · scope · time_window_start · time_window_end
  · findings_json · signal_summary_json(nullable) · created_at

reflection_proposals
  id · domain(memory|skill|knowledge_base) · kind · subject_user_id(nullable) · target_ref(nullable)
  · payload_json · reason · evidence_json · risk · status
  · reviewer_user_id · reviewed_at · rejection_reason · actor_user_id · applied_at
  · expires_at(nullable) · created_at · updated_at
```
- `domain` 区分域;`kind` 区分域内动作(memory: rewrite/merge/mark_stale/delete;skill: create/update/deprecate_skill;kb: archive_stale_doc/resync_connector)。
- `subject_user_id`:memory 的 owner(原 `user_id`);其余 nullable。便于"某用户的待审"筛选。
- `target_ref`:目标标识(skill 名 / kb document_id / connector_id);细节入 `payload_json`。
- `payload_json`:域特定载荷(memory: target_memory_ids+proposed_content+metadata_patch;skill: suggested_draft+suggested_diff;kb: 动作参数)。dataclass 层(`MemoryProposal`/`SkillProposal`/`KbProposal`)做类型化 ser/de。

### D2：apply 按 domain 分派,不复制状态机
统一 store 管 create/list/approve/reject + 通用状态转移;apply 调 `_APPLY_HANDLERS[domain](proposal)`:memory→memory public mutation API;skill→写 skill draft 边界;kb→knowledge-base public API(archive/resync)。**为何**:生命周期是共享行为(合表的根据),apply 是域特定代码(分派,不抄表)。

### D3：reports 1 张,理由是"日志无共享行为"
report 终态只读、无状态机、无外引用 → 事件日志的标准建模是 1 表 + type/domain 列。3 张只省信封、无行为收益,且 append-only 日志将来要拆极便宜。故 1 张。

### D4：KB v1 动作 = archive_stale_doc + resync_connector
选 KB 已有 public API、低风险、高价值的两个先打通"提案→审批→apply"闭环,证明三域对称跑得通;reingest/rerun_extraction/flag_gap 后续以新 kind+handler 增量加,不改表。

### D6：审批走 agent-owned 触达(复用层次 A)
三域提案审批**复用工具门那套** agent-owned 基础设施:`agent_config.resolve_approvers`(读 agent.yaml `ApprovalRouting`)解析**配置审批人(非 requester)** + `permission_gate._notify_approvers` 外呼 DM + Slack 按钮/文本决定,default-closed,全 agent 侧、**不走 platform console**。**为何不用 self-evolution-split 的 console 路由**:那是 2026-06-08 旧模型,已被 R1(`agent-owned-approval`)/`approval-suspend-resume`/`approval-requester-routing` supersede——审批早已统一为 agent 侧外呼,console 路由作废。
**复用层次 = A**:`reflection_proposals` 保留自己的提案生命周期(draft/diff/applied/expires,工具门的 `approvals` 没有),仅**触达**复用 resolve+notify,不并入 `approvals` 表(两者生命周期不同:工具门 in-run suspend-resume vs 提案 out-of-band)。
**out-of-band**:自进化提案系统生成、无活跃 run,故不复用 run suspend-resume;路径为 pending →（resolve+DM 审批人）→ approve/reject →（apply 按域分派)。

### D5：旧表退场、历史不迁移
`memory_maintenance_proposals` / `skill_proposals`(agent_state Y)+ `kb_reflection_reports`(alembic 027)退场。pending 提案是瞬态待办,按「上线前不迁移数据」新表全新建;部署方如需保留在制提案,切换前先 resolve/清空。

## Risks / Trade-offs

- [payload_json 失去列级类型] → 与 report 的 findings_json 一致;dataclass 层做校验;这些列本就不被 SQL 查询、只在 apply 时整体反序列化。
- [统一表混三域、一域 apply bug 触及他域行] → apply 严格按 domain 分派 + 域 handler 只认本域 kind;测试覆盖跨域隔离。
- [退场旧表丢失在制 pending] → 文档明示切换前清空;瞬态待办,可接受。
- [KB apply 误删/误同步] → 仅经 knowledge-base public API(archive 非物理删、resync 幂等);审批 default-closed;apply 前校验 target 存在。
- [统一 MIGRATIONS 版本竞争] → 取仓库当时 max+1;与其它动 Y 的 change 串行。

## Migration Plan

1. agent_state 统一 MIGRATIONS:append `reflection_reports` 加列(domain/signal_summary_json)+ 新建 `reflection_proposals` + drop `memory_maintenance_proposals`/`skill_proposals`。
2. alembic forward-drop `kb_reflection_reports`(027 孤儿)。
3. reflection.py:report 写 domain;统一 proposal store + 生命周期;apply 按域分派 handler;新增 generate_kb_proposals + kb apply(archive_stale_doc/resync_connector);memory/skill 提案改写统一表(保留 domain wrapper API)。
4. 同步 data-model §3.3(reflection 域 4→2 表)、reflection.md。
5. 回滚:agent_state Y 回退两表、恢复旧两表;alembic downgrade 重建 kb_reflection_reports;恢复代码(git)。

## Open Questions

- proposal 的 `kind` 取值是否需在 spec 固化为枚举,还是各 domain handler 自管?(倾向 handler 自管,表层只存字符串。)
