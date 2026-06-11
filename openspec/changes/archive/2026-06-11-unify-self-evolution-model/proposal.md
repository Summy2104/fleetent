## Why

自进化(self-evolution)有三域:**Memory / Skill / Knowledge Base**,但三者**所有权不同**——memory/skill 是 agent 自有(可读写),KB 是 ingest 单写、agent 只读的租户共享资源。当前数据模型没反映这点,且有缺陷:

- **报告层**:`reflection_reports`(memory+skill findings)与 `kb_reflection_reports`(KB findings)劈成两张,差异仅一个 nullable `signal_summary_json` 列——薄日志被过度拆分。
- **行动层**:Memory(`memory_maintenance_proposals`)、Skill(`skill_proposals`)各有提案审批表,**共享同一套生命周期(pending→approved/rejected→applied + reviewer/apply 审计)却抄了两遍**,命名不一致(`risk`/`risk_level`、`evidence_ids_json`/`evidence_refs_json`、`action`/`type`);Memory 还缺 review/apply 审计列。
- **skill apply 是死 stub**:`apply_skill_proposal_to_boundary` 直接 `raise not configured`——skill 提案能生成/审批但 apply 无落点。
- 附带 #4:`kb_reflection_reports` 在 alembic(管理库),而 reflection 写它走 `agent_state.db`,表对不上 → **KB 反思报告静默丢弃**。

## What Changes

按"**观察普适、行动只限 agent 自有**"收口成 **2 表内核**(均在 per-agent `agent_state.db`):

- **统一观察层 `reflection_reports`**(1 张 · **三域**):加 `domain`(memory/skill/knowledge_base)+ nullable `signal_summary_json`,吸收 `kb_reflection_reports`(修 #4)。agent 能读三者就能上报。终态只读日志、无生命周期。
- **统一行动层 `reflection_proposals`**(1 张 · **两域 memory/skill**):合并 `memory_maintenance_proposals` + `skill_proposals`,共享生命周期骨架 + `domain` 区分 + 域特定载荷入 `payload_json`;apply 按 `domain` 分派 handler。统一审批"收件箱"。
- **KB 只产 report、不进提案**:KB 是 agent 只读的租户共享资源,其 mutation(archive/re-extract/resync)不属 agent 侧;KB 的 remediation 由 **platform / 摄取面**承担(读 agent 的 KB report 投影后处理,**独立 change**)。connector + 凭证 + 写权限都在摄取面,不让 agent 持有。
- **接通 skill apply**(历史 stub):approved 的 skill 提案 apply 经 agent 侧 `skills.write_skill` 把**整个 skill bundle**(`SKILL.md` + 脚本/子目录,Agent Skill 标准协议)原子写进**该 agent 自己的** skills 目录 + 热更新;`update`=全树覆盖,`deprecate`=frontmatter `enabled:false` 软禁用;安全三层(审批 review bundle / SKILL.md 注入扫描 / 脚本经 sandbox)。取代 `raise not configured` stub。
- **审批走 agent-owned 触达**:memory/skill 提案审批**复用** agent-owned 审批人解析 + 外呼 DM(`agent_config.resolve_approvers` + `permission_gate._notify_approvers` / im_gateway),找**配置的审批人(memory→owner;skill→team/tenant 负责人;非 requester)**,default-closed,**不走 platform console**。提案系统生成、无活跃 run,故 out-of-band(审批人按钮/文本决定 → 触发 apply),不复用工具门 run suspend-resume。
- **命名/骨架对齐**:`risk`、`evidence_json`、`kind` 统一;memory/skill 生命周期一致。
- **退场**:`kb_reflection_reports`(alembic 027)、`memory_maintenance_proposals` / `skill_proposals`(agent_state Y)被统一两表替代。

## Capabilities

### New Capabilities
<!-- 无新增 capability;扩展既有 reflection -->

### Modified Capabilities
- `reflection`: 统一自进化数据模型(`reflection_reports` 三域观察 + `reflection_proposals` 两域 memory/skill 行动);接通 skill apply(全 bundle、agent-local);report/proposal 持久化改为统一两表(替代 `kb_reflection_reports` / `memory_maintenance_proposals` / `skill_proposals`);KB 仍只读(只产 report,不产 agent 侧提案、不在 agent 侧 mutate);memory/skill 审批触达复用 agent-owned `resolve_approvers` + 外呼 DM(非 requester、default-closed、不依赖 platform console)。
- `self-evolution-split`: 对齐审批路由——agent 自有域(memory→owner;skill→team/tenant 负责人)经 **agent-owned 外呼 DM**,取代原"skill/KB → platform console"旧路由(已被 R1 / approval-suspend-resume supersede);platform console 降为只读投影;**KB 移出 agent 侧审批门**(其 remediation 在平台/摄取面)。

## Impact

- **代码**:`reflection/reflection.py`(report 写 domain 三域、统一 proposal store/lifecycle 两域、按域 apply dispatch memory/skill、接通 skill apply)、`skills/`(新增 `write_skill` 公共边界)、`runtime/agent_state_migrations.py`(统一两表 schema、退场两张旧 proposal 表)、新增 alembic 迁移 drop `kb_reflection_reports`(027 孤儿)。
- **API**:proposal create/approve/reject/apply 收敛为按域分派的统一接口;`generate_memory_*` / `generate_skill_*` / `approve_*` / `apply_*` 保留为 domain wrapper。
- **owned tables**:`reflection_reports`(+domain/+signal_summary_json,三域)、`reflection_proposals`(新,两域,替代两张);`kb_reflection_reports` / `memory_maintenance_proposals` / `skill_proposals` 退场。
- **审批路由**:memory/skill 走 agent-owned 外呼 DM(非 requester、default-closed、全 agent 侧)。复用层次 A:`reflection_proposals` 保留自己的生命周期,仅触达复用工具门基础设施,不并入 `approvals` 表。
- **数据**:pending 提案瞬态——按「上线前不迁移数据」新表全新建、旧表退场;部署方如需保留在制提案,切换前先清空。
- **migration/shim**:agent_state Y append 统一两表 + drop 两张旧表(`CREATE TABLE IF NOT EXISTS` 幂等);alembic forward-drop `kb_reflection_reports`。
- **不在本切片**:**KB 的 mutation/remediation**(resync/re-extract/archive)——KB 是 agent 只读资源,变更在 platform/摄取面(独立 change,读 agent KB report 投影后处理);KB 接线 + 图谱 lift(`wire-kb-tenant-routing`);**Step 2 平台侧 skill 收集策展**(只读投影发现 agent-local 自进化 skill + 管理员收录提升 + 平台侧收录标记——单独 platform change);skill bundle 二进制资源(v1 限文本)。
