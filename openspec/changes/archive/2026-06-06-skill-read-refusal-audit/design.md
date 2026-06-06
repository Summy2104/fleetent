## Context

`read_skill(name)` 在 `builtin_tools.py`：查 `_index`，未知返回 error，`audit_blocked` 返回拒绝文本，否则 `load()`。拒绝分支不写日志，违反 skill-injection-audit spec 的审计要求。

`audit_log.write_audit(actor_user_id, action, target_type, target_id, detail)` 经 `user_store._conn`/`DB_PATH` 写——standalone agent 也用 user_store（bearer 认证），DB 可访问。

tool 通过声明 `tool_context: ToolContext | None = None` 参数 opt-in 上下文注入（registry.dispatch 检测后注入，不进 LLM schema）。`ToolContext` 有 `agent_name` / `session_id` / `features`。

## Goals / Non-Goals

**Goals:**
- `read_skill` 拒绝 audit_blocked skill 时写审计日志
- 日志含 skill 名、原因、可得的 session_id / agent_name
- 正常读取路径零新增开销（不写日志）

**Non-Goals:**
- 不改 audit_log 的 schema 或存储
- 不为 read_skill 引入 user_id 参数（tool 不持有 user_id；actor_user_id=None 可接受）
- 不审计"未知 skill 名"分支（那是 LLM 笔误，非安全事件）

## Decisions

### D1：action 命名 `skill.read_refused`

与现有 `skill.disable` / `skill.create` 等 skill 管理 action 同前缀，便于审计检索。target_type=`skill`，target_id=skill 名。

### D2：opt-in `tool_context` 丰富 detail

`read_skill(name, tool_context=None)`。拒绝时 detail 记 `{"reason": "audit_blocked", "session_id": ..., "agent_name": ...}`（context 缺失则对应字段为 None）。context 是 out-of-band 注入，不影响 LLM 看到的 schema。

### D3：仅拒绝分支写日志，保持热路径零开销

正常 `load()` 路径不写日志（高频）。只有 audit_blocked 拒绝（罕见）才写——审计价值高、开销可忽略。

### D4：审计写入失败不阻断拒绝返回

审计是旁路记录。若 `write_audit` 抛异常（DB 不可用等），捕获并 log warning，仍返回拒绝文本——拒绝行为（安全核心）不能因审计旁路失败而退化为放行或报错。

## Risks / Trade-offs

**[Risk] standalone agent 的 user_store DB 未初始化时 write_audit 失败**
→ D4 已规避：审计失败被捕获，拒绝照常返回。

**[Risk] audit_log 语义是"平台管理操作"，read_skill 是 agent 运行时事件**
→ 可接受：audit_log 表是通用 append-only 日志，按 action 字符串区分。skill.read_refused 是合理的安全审计事件。
