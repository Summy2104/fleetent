## Context

自进化三域(memory/skill/kb)当前 4 张表、不对称、有 spec 矛盾(详见 proposal)。决策原则:**按"是否共享行为"决定合表**——

- proposals 共享一套生命周期(状态机 + 审批/apply 审计)→ 合 1 张(否则抄三遍);域差异是不透明载荷,入 `payload_json`,apply 按域分派。
- reports 是终态只读日志、**无共享行为**;日志天然 1 张表 + `domain` 列,域差异入 `findings_json`。

结论:**2 表内核**(1 report + 1 proposal),均在 per-agent `agent_state.db`。

## Goals / Non-Goals

**Goals:**
- 收口为统一 `reflection_reports`(三域观察)+ `reflection_proposals`(两域 memory/skill 行动),退场旧表。
- 接通 skill apply(历史 stub → 全 bundle / agent-local,见 D7)。
- 修 #4(KB 报告并入统一 `reflection_reports`,不再静默丢)。

**Non-Goals:**
- **KB 的 mutation/remediation(resync / re-extract / archive)** —— KB 是 ingest 单写、agent 只读的租户共享资源,其变更不属 agent 侧;由 platform / 摄取面承担(读 agent 的 KB report 投影后处理),**独立 change**。本 change KB 只产 report(并入统一表),不产 agent 侧提案、不在 agent 侧 apply。
- KB 接线 + 图谱 lift(独立 change `wire-kb-tenant-routing`,动 kb.db)。
- 搬迁历史 pending 提案(瞬态,新表全新建)。
- **Step 2 平台侧 skill 收集策展**(平台只读投影发现 agent-local 自进化 skill + 管理员收录提升 + 平台侧收录标记)——单独 platform change;本 change 只做 agent 侧自写自用。
- skill bundle 的二进制资源(v1 限文本文件)。

## Decisions

### D1：2 表 schema（agent_state.db · 统一 MIGRATIONS）
```
reflection_reports
  id · domain(memory|skill|knowledge_base) · scope · time_window_start · time_window_end
  · findings_json · signal_summary_json(nullable) · created_at

reflection_proposals   （domain ∈ {memory, skill} —— 仅 agent 自有域）
  id · domain(memory|skill) · kind · subject_user_id(nullable) · target_ref(nullable)
  · payload_json · reason · evidence_json · risk · status
  · reviewer_user_id · reviewed_at · rejection_reason · actor_user_id · applied_at
  · expires_at(nullable) · created_at · updated_at
```
- `reflection_reports.domain` ∈ {memory, skill, knowledge_base}（观察三域）;`reflection_proposals.domain` ∈ {memory, skill}（行动仅 agent 自有域，**KB 不进提案表**）。
- `kind` 区分域内动作(memory: rewrite/merge/mark_stale/delete;skill: create/update/deprecate_skill)。
- `subject_user_id`:memory 的 owner(原 `user_id`);skill nullable。便于"某用户的待审"筛选。
- `target_ref`:目标标识(skill 名);细节入 `payload_json`。
- `payload_json`:域特定载荷(memory: target_memory_ids+proposed_content+metadata_patch;skill: 整个 bundle 文件树)。dataclass 层(`MemoryProposal`/`SkillProposal`)做类型化 ser/de。

### D2：apply 按 domain 分派,不复制状态机
统一 store 管 create/list/approve/reject + 通用状态转移;apply 调 `_APPLY_HANDLERS[domain](proposal)`:memory→memory public mutation API(已实现);skill→agent-local skills 目录写整个 bundle(见 D7,本 change 把历史 stub 接成真实现)。**仅 memory/skill 两个 handler**(KB 不在 agent 侧 apply,见 D4)。**为何**:生命周期是共享行为(合表的根据),apply 是域特定代码(分派,不抄表)。

### D7：Skill apply = 写 agent-local 的整个 skill bundle(接通历史 stub)
skill 是**目录 bundle**(`<name>/SKILL.md` + 可带脚本/子目录,Agent Skill 标准协议),不是单文件。skill apply SHALL 经 agent 侧 `skills.write_skill(name, files, provenance)` 公共边界把**整棵文件树**写进 **agent-local** skills 目录(`<agent home>/skills/<name>/`),**原子写**(先写临时目录 + SKILL.md 注入扫描 → rename 整目录换入,避免 registry 扫到半成品),SKILL.md 注入 frontmatter(`source: reflection` / `proposal_id` / `applied_at`),再 `registry.reload()` 热更新。**为何支持全 bundle 而非仅 SKILL.md**:只收录单文件没意义;安全靠三层——审批人 apply 前 review 整个 bundle(含脚本)+ SKILL.md 注入扫描 + skill 脚本执行时走 sandbox。**为何 agent-local**:各 agent 进化各自的、互不污染;跨 agent 共享靠 Step 2 平台只读策展收录(独立 change)。
- payload:`{ skill_name, kind, files: { relpath: content } }`(v1 限文本文件);**update = 全树覆盖**(proposal 携完整目标态,简单可靠;文件级 diff 是后续优化)。
- **deprecate = `enabled: false`**(frontmatter):从 catalog 排除→模型发现不到、不会自动误用;文件保留可追溯、可恢复(不物理删)。
- 审批触达 SHALL 让审批人能 review 整个 bundle(尤其脚本)再批。

### D3：reports 1 张,理由是"日志无共享行为"
report 终态只读、无状态机、无外引用 → 事件日志的标准建模是 1 表 + type/domain 列。3 张只省信封、无行为收益,且 append-only 日志将来要拆极便宜。故 1 张。

### D4：KB 不在 agent 侧 apply(所有权决定,非偷懒)
KB 关系库 = **ingest 单写、agent 只读(派生视图)、租户共享**(data-model §1)。其 mutation(archive / re-extract / resync)全是写操作,违反"agent 只读 KB";且 connector 属**摄取面**(凭证爆炸半径 + per-tenant 共享单例,不该每个 agent 进程持有)。**为何"三域对称"只在 report 成立、proposal 不成立**:观察普适(agent 能读三者→三域 report),但行动只限 **agent 自有**(memory/skill);KB 不是 agent 自有,故不进 proposal、不在 agent 侧 apply。**KB 自进化的闭环跨面**:agent 上报 KB report → platform 只读投影读到 → 摄取面/admin remediate(connector + 凭证 + 写权限都在那),独立 change,与 skill Step 2 同模式。

### D6：审批走 agent-owned 触达(复用层次 A)
memory / skill 提案审批**复用工具门那套** agent-owned 基础设施:`agent_config.resolve_approvers`(读 agent.yaml `ApprovalRouting`)解析**配置审批人(非 requester)** + `permission_gate._notify_approvers` 外呼 DM + Slack 按钮/文本决定,default-closed,全 agent 侧、**不走 platform console**。**为何不用 self-evolution-split 的 console 路由**:那是 2026-06-08 旧模型,已被 R1(`agent-owned-approval`)/`approval-suspend-resume`/`approval-requester-routing` supersede——审批早已统一为 agent 侧外呼,console 路由作废。
**复用层次 = A**:`reflection_proposals` 保留自己的提案生命周期(draft/diff/applied/expires,工具门的 `approvals` 没有),仅**触达**复用 resolve+notify,不并入 `approvals` 表(两者生命周期不同:工具门 in-run suspend-resume vs 提案 out-of-band)。
**out-of-band**:自进化提案系统生成、无活跃 run,故不复用 run suspend-resume;路径为 pending →（resolve+DM 审批人）→ approve/reject →（apply 按域分派)。

### D5：旧表退场、历史不迁移
`memory_maintenance_proposals` / `skill_proposals`(agent_state Y)+ `kb_reflection_reports`(alembic 027)退场。pending 提案是瞬态待办,按「上线前不迁移数据」新表全新建;部署方如需保留在制提案,切换前先 resolve/清空。

## Risks / Trade-offs

- [payload_json 失去列级类型] → 与 report 的 findings_json 一致;dataclass 层做校验;这些列本就不被 SQL 查询、只在 apply 时整体反序列化。
- [统一表混三域、一域 apply bug 触及他域行] → apply 严格按 domain 分派 + 域 handler 只认本域 kind;测试覆盖跨域隔离。
- [退场旧表丢失在制 pending] → 文档明示切换前清空;瞬态待办,可接受。
- [skill apply 写 bundle 半成品被 registry 扫到 / 误写他 agent 目录] → 原子写(临时目录→rename)、agent-local 限定路径;SKILL.md 注入扫描守门;审批人 review 整个 bundle。
- [统一 MIGRATIONS 版本竞争] → 取仓库当时 max+1;与其它动 Y 的 change 串行。

## Migration Plan

1. agent_state 统一 MIGRATIONS:append `reflection_reports` 加列(domain/signal_summary_json)+ 新建 `reflection_proposals` + drop `memory_maintenance_proposals`/`skill_proposals`。
2. alembic forward-drop `kb_reflection_reports`(027 孤儿)。
3. reflection.py:report 写 domain（三域，含 KB）;统一 proposal store + 生命周期（memory/skill）;apply 按域分派 handler（memory→已有;skill→接通全 bundle 写边界）;memory/skill 提案改写统一表(保留 domain wrapper API)。KB 仅产 report，不产提案、不 apply。
4. 同步 data-model §3.3(reflection 域 4→2 表)、reflection.md。
5. 回滚:agent_state Y 回退两表、恢复旧两表;alembic downgrade 重建 kb_reflection_reports;恢复代码(git)。

## Open Questions

- proposal 的 `kind` 取值是否需在 spec 固化为枚举,还是各 domain handler 自管?(倾向 handler 自管,表层只存字符串。)
