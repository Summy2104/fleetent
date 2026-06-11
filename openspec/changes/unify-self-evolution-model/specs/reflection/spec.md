## ADDED Requirements

### Requirement: 统一自进化数据模型（report 三域 · proposal 两域）
自进化 SHALL 用**两张表**:统一**观察层** `reflection_reports`（终态只读日志，覆盖三域 memory / skill / knowledge_base——**观察普适**，agent 能读三者就能上报）+ 统一**行动层** `reflection_proposals`（共享审批生命周期，**仅 agent 自有域 memory / skill**）。**KB 不进 `reflection_proposals`**:KB 关系库是 ingest 单写、agent 只读的**租户共享资源**，其 mutation 不属 agent 侧;KB 的 remediation 由 platform / 摄取面承担（读 agent 的 KB report 投影后执行，独立 change）。两表均含 `domain` 列区分域;域特定内容入 JSON 载荷（report 的 `findings_json`、proposal 的 `payload_json`），不为每域单建表。`reflection_proposals` SHALL 提供单一生命周期(status: pending→approved/rejected→applied)与审批审计列（reviewer/applied），memory / skill 共用;apply SHALL 按 `domain` 分派 handler（memory / skill），不复制状态机。

#### Scenario: 报告统一一张表、三域
- **WHEN** memory / skill / KB reflection 各生成报告
- **THEN** 三者均写入同一 `reflection_reports` 表，以 `domain` 区分，不存在 per-域报告表

#### Scenario: 提案统一一张表、仅 agent 自有两域
- **WHEN** memory 或 skill 生成提案
- **THEN** 写入同一 `reflection_proposals` 表（`domain` ∈ {memory, skill}），经同一套 approve/reject/apply 生命周期处理;域特定数据在 `payload_json`，apply 按 `domain` 分派

#### Scenario: KB 不产 agent 侧提案
- **WHEN** KB reflection 产生 finding
- **THEN** 系统不在 `reflection_proposals` 创建 `domain=knowledge_base` 行，也不在 agent 侧 apply KB mutation;KB finding 仅以 report 形式记录，remediation 留给 platform / 摄取面

#### Scenario: 统一审批收件箱
- **WHEN** 列出待审提案
- **THEN** 一次查询返回跨 memory / skill 的 pending 提案（按 `domain` 可筛），不需 union 多表

### Requirement: Skill 自进化 apply 写 agent-local bundle
approved 的 skill 提案 apply SHALL 经 agent 侧 `skills` 公共边界把**整个 skill bundle**（`<name>/SKILL.md` + 可带脚本/子目录/文本资源，Agent Skill 标准协议）写进**该 agent 自己的** skills 目录（`<agent home>/skills/<name>/`），并热更新（`registry.reload()`）。写入 SHALL **原子**（先写临时目录 + SKILL.md 注入扫描通过 → 整目录 rename 换入，registry MUST NOT 扫到半成品）。SKILL.md SHALL 带 provenance frontmatter(`source: reflection` / `proposal_id` / `applied_at`)。apply MUST NOT 写其它 agent 的目录、MUST NOT 经 platform（agent-local、自洽）。`update_skill` SHALL 以**全树覆盖**目标 skill;`deprecate_skill` SHALL 以 frontmatter `enabled: false` 软禁用（从 catalog 排除、模型不再发现/自动调用，文件保留可追溯），不物理删。安全由三层保证:审批人 apply 前 review 整个 bundle + SKILL.md 注入扫描 + 脚本执行经 sandbox。

#### Scenario: apply 写整个 bundle 到 agent 自己的 skills 目录
- **WHEN** 一个 approved 的 `create_skill` 提案 apply
- **THEN** 系统把 payload 的整棵文件树（SKILL.md + 脚本等）原子写入 `<agent home>/skills/<name>/` 并 `registry.reload()`，该 skill 立即可用，且不触及其它 agent 的目录

#### Scenario: SKILL.md 注入扫描守门
- **WHEN** 提案的 SKILL.md 命中 severe 注入模式
- **THEN** apply 拒绝写入，提案不进入 applied

#### Scenario: deprecate 软禁用、模型不误用
- **WHEN** 一个 `deprecate_skill` 提案 apply
- **THEN** 该 skill 的 SKILL.md frontmatter 置 `enabled: false`，从 catalog 排除，模型不再发现/自动调用;文件保留

### Requirement: 自进化提案审批走 agent-owned 触达
memory / skill 提案的审批触达 SHALL 复用 **agent-owned** 审批基础设施——经 `agent_config.resolve_approvers`(读 agent.yaml `ApprovalRouting`)解析**配置的审批人**(memory→该记忆 owner;skill→team/tenant 负责人)并经 im_gateway **外呼 DM**(沿用工具门的 `permission_gate._notify_approvers` 路径),审批人经 Slack 按钮 / 文本命令决定。审批人 SHALL **默认为非 requester 的真实负责人/owner**(系统生成的提案无 requester);找不到审批人 SHALL **default-closed**(不自动 apply)。审批触达 MUST 全在 agent 侧,MUST NOT 依赖 platform console。提案审批是 **out-of-band**(无活跃 run),不复用工具门的 run suspend-resume;审批通过后由 apply(按 domain 分派)执行。

#### Scenario: 提案外呼配置审批人、非当前人
- **WHEN** memory 或 skill 提案进入 pending
- **THEN** 系统经 `resolve_approvers` 解析 agent 配置的审批人(memory→owner;skill→team/tenant 负责人)并经 im_gateway DM 之，不路由给该提案的发起者本人

#### Scenario: 无审批人 default-closed
- **WHEN** 配置中解析不到可达审批人
- **THEN** 提案保持 pending、不被自动 apply（default-closed），不回退到 platform console

#### Scenario: 全 agent 侧、不依赖 platform
- **WHEN** standalone agent（无 platform）运行自进化审批
- **THEN** 审批人解析与 DM 触达全在 agent 侧完成，不调用 platform console

## MODIFIED Requirements

### Requirement: Reflection report persistence
系统 SHALL 可以保存 reflection report，且保存内容不得包含完整 trace transcript。report SHALL 持久化在统一 `reflection_reports` 表，以 `domain`(memory / skill / knowledge_base)区分;KB report 复用 nullable `signal_summary_json` 列。不再为各域单建报告表。

#### Scenario: Migration creates reflection_reports
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 reflection-owned `reflection_reports` 表（含 `domain` 列），且不含独立的 `kb_reflection_reports` 表

#### Scenario: Persisted report omits raw transcript
- **WHEN** report 被保存
- **THEN** 保存的 payload 包含 finding summary、evidence ids 和 metadata
- **AND** 不包含完整用户对话 transcript

### Requirement: Knowledge-base reflection persistence
系统 SHALL 持久化 KB reflection reports，且不得保存完整用户 transcript 或完整文档正文。KB report SHALL 写入统一 `reflection_reports` 表（`domain=knowledge_base`），不再使用独立 `kb_reflection_reports` 表。KB reflection 仍为**只读**(不在 agent 侧 mutate KB、不创建 agent 侧 KB proposal);KB 的 remediation 由 platform / 摄取面承担。

#### Scenario: KB 报告写入统一表
- **WHEN** 数据库 migration 运行到最新版本，且 KB reflection report 被保存
- **THEN** report 落在 `reflection_reports`（`domain=knowledge_base`），数据库不含 `kb_reflection_reports` 表

#### Scenario: Persisted payload is redacted
- **WHEN** KB reflection report 被保存
- **THEN** payload 只包含 finding summary、evidence ids、短摘要和 metadata
- **AND** 不包含完整用户对话 transcript 或完整文档正文
