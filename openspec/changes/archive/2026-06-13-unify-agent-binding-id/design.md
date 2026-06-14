# unify-agent-binding-id Design

## Context

身份模型迁移阶段 2（见 `docs/architecture/agent-identity-model.md`）。已核实：`agent_kbs.agent_id` / `agent_skills.agent_id` 为 TEXT 存 `str(agent.id)`，两表无 FK。`agent_skills` 写读分叉：
- 写：`skill_admin_api:470` 传 `str(id)`；`agent_admin_api`（控制台）`set_agent_skill:283` 与列表 `:265-268` 传 **name**
- 读：`materialize:140-141` `has_any_binding(str(agent.id))` / `enabled_skill_names(str(agent.id))` 按 id
→ 控制台（name）写的绑定 materialize（id）读不到，静默失效。
当前 alembic head = 081。规范键 = `agents.id`（消费方 materialize 即按它读）。

## Goals / Non-Goals

**Goals:**
- `agent_kbs` / `agent_skills` 的 agent 引用规整为 INTEGER `agents.id` + FK ON DELETE CASCADE
- 修 `agent_skills` name/id 混写 bug：任一 admin 路径设的绑定 materialize 可见
- 补这两表缺失的孤儿保护（FK cascade）

**Non-Goals:**
- 不碰 agent 侧 / traces（阶段 1）、admin_state·session_meta（阶段 3）、其余绑定表 FK（阶段 4）、翻译边界固化（阶段 5）
- 不改 HTTP 路由对外形态（仍按 `{name}` 寻址，内部解析 name→id）
- 不改 binding 的业务行为（绑定/解绑/查看/审计语义不变）

## Decisions

**D1：规范键 = 整数 `agents.id`，控制台写路径补 name→id 解析**
materialize（运行时消费方）已按 `agent.id` 读，故 id 是事实规范键。bug 根因是控制台写路径用 name。修法：控制台 `set_agent_skill` / skill 列表在调 store 前 `agent_store` 解析 name→id；`skill_admin_api` 去 `str()` 传 int。不反过来让 materialize 按 name 读（那会把规范键定成可变的 name，违背身份模型）。

**D2：列类型转换 + 数据迁移在一个 Alembic 迁移内（append after 081，不硬编码）**
SQLite 改列类型走 batch（重建表）。数据迁移：
- `agent_kbs`：`agent_id` 数字串 `CAST` → INTEGER（值本就是 id 串，无损）
- `agent_skills`：数字串 `CAST` → INTEGER；`agent_id` 为 name 串的行（控制台 bug 产物）`JOIN agents ON agent_skills.agent_id = agents.name` 解析为 `agents.id`，解析不到的行**丢弃**（这些行本就 materialize 看不到、静默失效）
- 两表加 FK→agents.id ON DELETE CASCADE
downgrade 回 TEXT（值转回字符串）。pre-launch 窗口、存量可重置。

**D3：store 参数 int 化，SQL 不变**
`skill_admin_store` / `agent_kbs_store` 的 `agent_id` 形参类型 str→int；named-param SQL 文本不变（SQLite 按值绑定）。调用方传 `agent.id`（int）。

## Risks / Trade-offs

- [控制台仍有路径漏改 name→id → bug 残留] → 全仓 grep 控制台/skill/kb 对这俩 store 的调用点逐一核；**回归测试：控制台 PUT 绑定后 materialize 能读到**（直接覆盖 bug 修复）
- [迁移把 name 串行误 CAST 成 0/NULL] → 迁移显式分流：纯数字串 CAST、非数字（name）走 agents 解析、解析不到丢弃；升级路径测试覆盖三类行（数字串 / 可解析 name / 不可解析）
- [FK ON DELETE CASCADE 误删] → 语义正确（agent 没了其绑定本就该没）；与既有 agent 删除路径对照测试无新增失败
- [TEXT→INTEGER batch 重建丢索引/约束] → 迁移重建时保留复合主键 / 唯一约束（agent_kbs 的 (tenant_id,kb_id,agent_id)、agent_skills 的 (agent_id,skill_name)）；schema 断言测试

## Migration Plan

Alembic 新迁移（append after 081）：batch 重建两表 agent_id 列为 INTEGER + 数据迁移（CAST / name 解析 / 丢弃）+ 加 FK。代码（store 参数 + 控制台解析 + 去 str 包装）同 change。回滚 = downgrade（INTEGER→TEXT、去 FK）；pre-launch 可重置。

## Open Questions
（无——规范键、bug 修法、迁移分流均依身份模型 design doc 与用户敲定。）
