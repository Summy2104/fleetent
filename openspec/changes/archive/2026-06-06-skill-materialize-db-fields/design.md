## Context

Agent 进程只读 `agent.yaml`，从不访问 platform DB（解耦原则）。因此 platform 的 skill 管理决策要影响 agent，唯一通路是 materialize：把 DB 状态写进 agent.yaml。

当前 `agent_file_from_store()` 只传了 `allowed_skills=agent.allowed_skills`（authored 值），漏掉两个 DB 来源：
- `skill_admin_state.global_enabled=0` → 应映射到 `AgentFile.disabled_skills`
- `agent_skills` 绑定矩阵 → 应映射到 `AgentFile.allowed_skills`（覆盖 authored 值）

两个 store 方法已存在：`list_states()` 返回含 `global_enabled` 的行；`enabled_skill_names(agent_id: str)` 返回该 agent enabled=1 的 skill 名集合。

## Goals / Non-Goals

**Goals:**
- materialize 把全局 disabled skills 写入 `disabled_skills`
- materialize 把 per-agent 绑定写入 `allowed_skills`，无绑定时回退 authored 值
- 纯增量：不改动 agent runtime 对这两个字段的既有读取语义

**Non-Goals:**
- 不在此 change 触发 re-materialize（admin 操作后的自动刷新是 Change 3）
- 不改动 agent runtime 对 `disabled_skills` / `allowed_skills` 的消费逻辑（已实现）
- 不处理 skill 文件分发（Change 4）

## Decisions

### D1：`disabled_skills` 取全局 disabled 的并集

`list_states()` 返回所有管理状态行；筛 `global_enabled == 0` 的 `skill_name`。所有 agent 共享同一份全局 disabled 列表，因为全局 disable 是平台级决策。

### D2：`allowed_skills` 的绑定优先 + 回退语义

```
bound = enabled_skill_names(str(agent.id))   # agent_skills 中 enabled=1 的集合
if bound:                                    # 有任意绑定行 → 用绑定子集
    allowed_skills = sorted(bound)
else:                                        # 无绑定 → 回退 authored 值
    allowed_skills = agent.allowed_skills
```

`agent.id` 是 int，`enabled_skill_names` 接收 str，故 `str(agent.id)`。排序保证 yaml 输出确定性（便于 diff 和测试）。

注意 `enabled_skill_names` 只返回 enabled=1 的行，无法区分"无绑定"与"有绑定但全部 disabled"。用 `has_any_binding(str(agent.id))` 判断是否有绑定行更精确：有绑定行时即使 enabled 集合为空也应使用空集（该 agent 被显式收窄到无 skill），而非回退 authored 值。

### D3：用 has_any_binding 判定回退，而非 bound 是否为空

```
if skill_admin_store.has_any_binding(str(agent.id)):
    allowed_skills = sorted(skill_admin_store.enabled_skill_names(str(agent.id)))
else:
    allowed_skills = agent.allowed_skills
```

这样"管理台把某 agent 的所有 skill 都关掉"会正确产出空 `allowed_skills`（catalog 收窄到无），而不是错误地回退到 authored 全集。

## Risks / Trade-offs

**[Risk] `agent_skills` / `skill_admin_state` 表不存在（旧库）**
→ 与 `_knowledge_for_agent` 处理 `agent_kbs` 缺表一致：捕获 `sqlite3.OperationalError`（no such table）并回退到 authored 值/空 disabled 列表。

**[Risk] 空 `allowed_skills` 的语义歧义**
→ D3 已解决：用 `has_any_binding` 区分"无绑定回退"与"绑定为空收窄"。
