## Context

`engine_observability(skill_name)` 在 skill_admin_api 是占位符返回 stale 空数据。无命中记录表。`read_skill`（builtin_tools）成功加载 skill 是天然的"命中"信号点，且已能经 `tool_context` 拿到 agent_name/session_id（Change A 已让 read_skill opt-in tool_context）。`skill_admin_store` 是 skill 管理持久化边界（named params，Alembic 管 schema）。

## Goals / Non-Goals

**Goals:**
- 每次 read_skill 成功加载落一条命中记录
- observe(skill_name) 返回真实 hits 计数 + 去重 session 列表
- engine_observability 返回真实数据替换 stale 占位符
- 记录是 best-effort，绝不阻断 read_skill 正常返回

**Non-Goals:**
- 不记录 read_skill 的失败/拒绝（那是 Change A 的审计日志职责）
- 不做时间窗口聚合 / 按 agent 分组统计（当前只需 hits + sessions；未来可扩展）
- 不在 read_skill 热路径做同步昂贵查询（只 INSERT 一行）

## Decisions

### D1：新表 `skill_hits`，migration 057

```
skill_hits(id INTEGER PK AUTOINCREMENT, skill_name TEXT NOT NULL,
           agent_id TEXT, session_id TEXT, triggered_at TEXT NOT NULL)
+ index on skill_name（observe 按 skill_name 聚合）
```
append-only 命中流水；agent_id/session_id 可空（CLI 无 session 时）。Alembic 管 schema，store 不建表。

### D2：命中点在 read_skill 成功 load 之后

`read_skill` 在 `return skill_registry.load(name)` 前记录。只记成功加载（audit_blocked / 未知名分支不记——前者是 Change A 的拒绝审计，后者是笔误）。`record_hit` 包在 try/except：DB 不可用 / 表缺失等失败记 warning，read_skill 仍返回正文。import 放函数内避免 builtin_tools → platform 的循环依赖。

### D3：observe(skill_name) 返回 {skill_name, hits, sessions, stale:False}

`hits` = `COUNT(*)`；`sessions` = `SELECT DISTINCT session_id WHERE session_id IS NOT NULL`。`stale: False` 表示真实数据（占位符是 True）。结构与原占位符兼容（admin_api 直接透传）。

### D4：engine_observability 改调 observe

`skill_admin_api.engine_observability(skill_name)` 从返回 stale 占位符改为 `return skill_admin_store.observe(skill_name)`。一行替换，与 Change 1 修 engine_reload/engine_audit 同模式。

## Risks / Trade-offs

**[Risk] read_skill 热路径每次多一次 DB INSERT**
→ 可接受：read_skill 本就是低频（模型显式调用加载 skill），单行 INSERT 开销可忽略；且 best-effort try/except 保证即使 DB 慢/错也不影响功能。

**[Risk] skill_hits 无限增长**
→ 当前不做保留策略（YAGNI）；append-only 流水表，未来可加 TTL 清理（与 traces/session 清理同模式）。记入决策文档供后续。

**[Risk] standalone agent 的 DB 与 platform DB 是否同一**
→ read_skill 经 skill_admin_store → create_database(Settings().database_url)，与 audit_log 同样落 agent 自己的 DB（standalone）或 platform DB（平台）。observe 查同一 DB。自洽。
