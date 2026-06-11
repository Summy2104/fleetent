## Why

自进化(self-evolution)有三域:**Memory / Skill / Knowledge Base**。当前数据模型不对称、且有一处 spec 矛盾:

- **报告层**:`reflection_reports`(memory+skill findings)与 `kb_reflection_reports`(KB findings)劈成两张,差异仅一个 nullable `signal_summary_json` 列——薄日志被过度拆分。
- **行动层**:Memory(`memory_maintenance_proposals`)、Skill(`skill_proposals`)各有提案审批表,**三域共享同一套生命周期(pending→approved/rejected→applied + reviewer/apply 审计)却抄了两遍**,且命名不一致(`risk`/`risk_level`、`evidence_ids_json`/`evidence_refs_json`、`action`/`type`);Memory 还缺 review/apply 审计列。
- **KB 行动层缺失 + spec 矛盾**:`reflection` spec 说"KB reflection 只读、不创建 KB proposal",但 `self-evolution-split` spec 已规定"skill 与 **KB** → platform console 审"——**KB 提案本是既定设计意图,只是没实现**。
- 附带 #4:`kb_reflection_reports` 物理在 alembic(管理库),而 reflection 写它走 `agent_state.db`,表对不上 → **KB 反思报告当前静默丢弃**。

## What Changes

把自进化收口成**对称的 2 表内核**(均在 per-agent `agent_state.db`),并补齐 KB 自进化:

- **统一观察层 `reflection_reports`**(1 张):加 `domain`(memory/skill/kb)+ nullable `signal_summary_json`,吸收 `kb_reflection_reports`(顺带修 #4)。终态只读日志,无生命周期。
- **统一行动层 `reflection_proposals`**(1 张):合并 `memory_maintenance_proposals` + `skill_proposals`,共享生命周期骨架(status/review/apply 审计)+ `domain` 区分 + 域特定载荷入 `payload_json`;apply 按 `domain` 分派 handler。统一审批"收件箱"。
- **补 KB 自进化**(`domain=kb`):KB findings 生成 KB mutation proposals(v1 动作:`archive_stale_doc`、`resync_connector`),审批后经 knowledge-base public API 执行。
- **审批走 agent-owned 触达**:三域提案的审批一律**复用** agent-owned 审批人解析 + 外呼 DM(`agent_config.resolve_approvers` + `permission_gate._notify_approvers` / im_gateway),找**配置的审批人(team/tenant 负责人,非 requester)**,default-closed;**不走 platform console**。自进化提案是系统生成、无活跃 run,故为 out-of-band(审批人按钮/文本决定 → 触发 apply),不复用工具门的 run suspend-resume。
- **命名/骨架对齐**:`risk`、`evidence_json`、`kind` 统一;三域生命周期一致。
- **退场**:`kb_reflection_reports`(alembic 027)、`memory_maintenance_proposals` / `skill_proposals`(agent_state Y)被统一两表替代。

## Capabilities

### New Capabilities
<!-- 无新增 capability;扩展既有 reflection -->

### Modified Capabilities
- `reflection`: 统一自进化数据模型(1 `reflection_reports` + 1 `reflection_proposals`,三域 memory/skill/kb);KB reflection 由"只读"改为"可生成 KB mutation proposal(审批后经 public API 执行,仍不自动改 KB)";report/proposal 持久化改为统一两表(替代 `kb_reflection_reports` / `memory_maintenance_proposals` / `skill_proposals`);三域审批触达统一复用 agent-owned `resolve_approvers` + 外呼 DM(非 requester、default-closed、不依赖 platform console)。
- `self-evolution-split`: 对齐审批路由——按影响范围解析审批人(memory→owner;shared/skill/KB→team/tenant 负责人),但触达渠道统一为 **agent-owned 外呼 DM**,取代原"skill/KB → platform console"旧路由(已被 R1 / approval-suspend-resume supersede);platform console 降为只读投影。

## Impact

- **代码**:`reflection/reflection.py`(report 写 domain、统一 proposal store/lifecycle、按域 apply dispatch、新增 KB 提案生成 + apply handler)、`runtime/agent_state_migrations.py`(统一两表 schema、退场两张旧 proposal 表)、新增 alembic 迁移 drop `kb_reflection_reports`(027 孤儿)。
- **API**:proposal 的 create/approve/reject/apply 收敛为按域分派的统一接口;`generate_memory_maintenance_proposals` / `generate_skill_proposals` 保留为 domain wrapper;新增 `generate_kb_proposals` / KB apply handler。
- **owned tables**:`reflection_reports`(+domain/+signal_summary_json)、`reflection_proposals`(新,替代两张);`kb_reflection_reports` / `memory_maintenance_proposals` / `skill_proposals` 退场。
- **审批路由(修正)**:三域统一走 **agent-owned** —— `resolve_approvers`(读 agent.yaml `ApprovalRouting`)解析配置审批人(非 requester)+ im_gateway 外呼 DM + Slack 按钮/文本决定,default-closed,**全 agent 侧、不依赖 platform console**(取代 `self-evolution-split` 旧的"console"路由,该 spec 已被 R1/approval-suspend-resume supersede)。**复用层次 = A**:`reflection_proposals` 保留自己的提案生命周期(draft/diff/applied),仅**触达**复用工具门那套基础设施,不并入 `approvals` 表。
- **数据**:pending 提案是瞬态待办——按「上线前不迁移数据」**新表全新建、旧表退场**(不搬历史 pending);如需保留在制提案,部署方在切换前先清空。
- **migration/shim**:agent_state Y append 统一两表 + drop 两张旧表(`CREATE TABLE IF NOT EXISTS` 幂等);alembic forward-drop `kb_reflection_reports`。
- **不在本切片**:KB 接线 + 图谱 lift(独立 change `wire-kb-tenant-routing`,动 kb.db);KB v1 之外的提案动作(reingest/rerun_extraction/flag_gap 后续加 handler 即可,不改表)。
