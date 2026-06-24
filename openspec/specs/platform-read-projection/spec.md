# platform-read-projection Specification

## Purpose

控制面（platform）对 agent 侧物理库的统一只读投影机制：只读 router 句柄（不迁移）+ 共享 store 读函数 + management.db registry 发现/遍历聚合。禁物化副本、禁 agent 反向写（target-architecture.md §7 落地）。
## Requirements
### Requirement: platform 只读 agent 侧库

platform SHALL read agent-side physical databases through read-only connections only — never writing, never migrating. Discovery uses the management DB registry; each agent's DB is opened via tenant-first router `agent_scope(tenant_id, agent_name).open_*_ro()`.

#### Scenario: Session projection opens tenant-first state DB read-only
- **WHEN** platform aggregates sessions for tenant `acme` agent `support`
- **THEN** it opens `tenants/acme/agents/support/data/agent_state.db` read-only through router
- **AND** it does not migrate or write that DB

#### Scenario: Missing agent DB is skipped
- **WHEN** an agent has never booted and its tenant-first DB file does not exist
- **THEN** platform projection skips it without creating the DB

#### Scenario: Projection does not use old data layout
- **WHEN** platform reads traces, approvals, sessions, or agent memory
- **THEN** it does not look under `data/<tenant>/<agent>/`

### Requirement: 经共享读函数 + registry 发现

platform SHALL 经 **agent 侧 store 的共享只读查询函数**读取（不手写 SQL，schema 随读函数同仓同改），并经 `management.db` registry 发现主体/agent、遍历聚合跨 agent/主体的视图。

#### Scenario: 经读函数而非手写 SQL

- **WHEN** platform 读 agent 侧某 store
- **THEN** 调用该 store 的共享只读查询函数（喂只读连接），而非 platform 内手写 SQL

#### Scenario: registry 遍历聚合

- **WHEN** platform 需跨多 agent/主体聚合（如统计/审批列表）
- **THEN** 经 registry 枚举 → 逐个只读开 → 应用层聚合

### Requirement: 各资源投影语义

approvals 投影 SHALL join 身份（agent 侧不透明 actor → 真实身份经 #4/management 解析）；user memory 投影 SHALL 跨该 user 谈过的 agent 遍历（内容投影可选）；**agent memory 投影 SHALL per-agent 直读**（读该 agent 的 agent memory 库，不再 per-tenant 直读、不跨 agent 聚合）。

#### Scenario: approvals 投影解析身份

- **WHEN** platform 投影审批历史
- **THEN** 读 agent 侧 approval_store（只读）+ join 身份解析出"谁批的"（#4 落地后）

#### Scenario: agent memory per-agent 直读

- **WHEN** platform 投影某 agent 的 agent memory
- **THEN** 只读该 agent 的 agent memory 库（经 per-agent 只读句柄），不 per-tenant 聚合、不遍历其它 agent

### Requirement: agent 侧数据读投影经 name→id 解析（读翻译边界）
agent 侧物理产物（traces、sessions 等）以 agent **name** 标 agent（身份模型 R2）；平台关系层以 `agents.id` 为身份（R1）。故 platform 读 agent 侧 name-keyed 数据并关联回平台 agent 时，SHALL 经 `agents` 表做 **name→id 解析**，且该翻译 SHALL 收口在读投影 / observability 读路径一处，不散落到其它代码。

#### Scenario: 按平台 agent_id 投影其 agent 侧 trace
- **WHEN** platform 投影某 agent（持 `agents.id`）的 trace
- **THEN** 经 `agents` 解析出该 agent 的 name，再按 name 读 agent 侧 traces；结果关联回该 `agents.id`

#### Scenario: 翻译收口
- **WHEN** 审视平台读 agent 侧数据的代码路径
- **THEN** name↔id 翻译只出现在读投影 / observability 读边界（与 materialize 写边界并列的唯二翻译点），不在其它模块重复

