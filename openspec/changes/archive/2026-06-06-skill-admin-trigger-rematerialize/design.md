## Context

`skill-materialize-db-fields` 已让 `agent_file_from_store()` 读 DB 写 agent.yaml。缺的是触发：admin 改 skill 状态后没人调 materialize。

三个写接口的影响面不同：
- `disable_skill` / `enable_skill`：改 `skill_admin_state.global_enabled` → 影响**所有** agent 的 `disabled_skills`
- `set_skill_agent_binding`：改 `agent_skills` 某行 → 只影响**一个** agent 的 `allowed_skills`

`materialize.py` 已有 `materialize_from_store(name)`（按名 re-export 单个 agent）。需要补一个全量版本，以及 `agent_store` 的名字列举方法。

## Goals / Non-Goals

**Goals:**
- admin skill 写操作后，受影响 agent 的 agent.yaml 自动刷新
- 全局操作刷新所有 agent，绑定操作只刷新对应 agent
- re-materialize best-effort：单个 agent 失败被记录但不阻断接口或其余 agent

**Non-Goals:**
- 不向运行中的 agent 进程发送 reload 信号（agent 重启/reload 是独立运维动作；本 change 只保证落盘的 agent.yaml 是最新的）
- 不改动 materialize 的写入逻辑本身（Change 2 已完成）

## Decisions

### D1：`list_all_names()` 用 store 边界查询

```python
def list_all_names() -> list[str]:
    rows = _db().execute("SELECT name FROM agents ORDER BY name").fetchall()
    return [r["name"] for r in rows]
```

排序保证确定性，便于测试。

### D2：`rematerialize_all()` best-effort，返回成功列表

```python
def rematerialize_all() -> list[str]:
    done: list[str] = []
    for name in agent_store.list_all_names():
        try:
            if materialize_from_store(name) is not None:
                done.append(name)
        except Exception as exc:  # noqa: BLE001 — one agent's failure must not block others
            _logger.warning("rematerialize_failed", agent=name, error=str(exc))
    return done
```

与 controller 的 best-effort 风格一致：一个 agent 的 materialize 失败（缺 provider、磁盘错误等）不应阻断其他 agent 或让 admin 接口报 500。

### D3：绑定接口用 `get_agent_name_by_id` 解析 name

`set_skill_agent_binding` 接收的是 `agent_id: str`（URL 路径参数），而 `materialize_from_store` 按 name 操作。用 `agent_store.get_agent_name_by_id(int(agent_id))` 解析；解析失败（无此 agent）则跳过 re-materialize（绑定行仍写入，幂等）。

### D4：触发点放在审计日志之后

接口顺序：写 DB → 写审计 → 触发 re-materialize。re-materialize 是副作用补偿，放最后，即使它失败，DB 写入和审计已完成，下次手动 materialize 仍能补齐。

## Risks / Trade-offs

**[Risk] 全量 re-materialize 在 agent 数量大时慢**
→ 可接受：skill 全局 enable/disable 是低频管理操作。若未来 agent 数过大，可改为只 re-materialize 引用了该 skill 的 agent，但当前 YAGNI。

**[Risk] re-materialize 覆盖 operator 手改的 agent.yaml**
→ 已知行为：agent.yaml 是 DB 的导出产物，手改本就会被下次 materialize 覆盖（与现有 `materialize_from_store` 语义一致）。operator 的真实配置源是 DB / .env，不是 agent.yaml。
