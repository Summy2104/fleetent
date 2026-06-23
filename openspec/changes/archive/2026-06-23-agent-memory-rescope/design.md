## Context

`shared_memory` 现状（探索核实）：

- **半成品/未接通**：`mark_shared_memory_proposal_applied` 只标状态、不调 `create_shared_memory`（全库零调用方）；`build_context` 不查它；per-agent home 的 `shared_memory.db` 是空表。
- **作用域定错**：被建成 per-tenant 资源——`tenant_router.tenant_scope().open_shared_memory_db()` 解析、`agent-db-schema-self-init` 标 `shared_memory.db` 为 tenant-scoped、`platform-read-projection` 规定"shared memory per-tenant 直读"、表 `shared_memory_items` 带 `scope_type ∈ {team,tenant}` / `scope_id`。但物理上每 agent home 各一份 → 既没真共享，scope 模型也没人消费。

探索决策（`docs/architecture/agent-home-layout.md` ledger E）：跨 agent/跨租户共享归 **KB**（受治理）；这块正名 **agent memory**、收成 **agent 级**。三层记忆正交：`per-(agent×user)` user memory / `per-agent` agent memory / `per-tenant 治理` KB。

约束：agent 运行时模块 MUST NOT import `fleetent.platform.*`（铁律）；`memory` MUST NOT import `reflection`（既有护栏）。

## Goals / Non-Goals

**Goals:**
- 正名 `shared_memory` → `agent_memory` 全链路。
- 重作用域：per-tenant（`tenant_scope`）→ per-agent（`agent_scope`），删 `scope_type`/`scope_id`。
- platform 投影改 per-agent 直读。
- 净化半成品命名，不留 shim（无消费者）。

**Non-Goals:**
- **不**把 agent memory 接进 `build_context` 读注入（功能接通，半成品另一半，单独立项）。
- **不**做 tenant-first 整体目录布局重构（另一片）。
- 不改 reflection 自进化/审批/管理的公共 API 行为（只换术语 + 落地的真相源作用域）。

## Decisions

### D1 — 重作用域：agent memory 从 `tenant_scope` 移到 `agent_scope`

`tenant_router` 删 `open_shared_memory_db`（per-tenant），改由 `agent_scope(tenant, agent_id)` 暴露 agent memory 句柄。`_init_agent_db_schema` 不再建 tenant-scoped `shared_memory.db`，改建 **per-agent `agent_memory.db`**（经 `agent_scope`，与 `agent_state.db`/`agent_vectors.db` 平级）。
**为何**：agent 级语义 = per-agent 物理库；与 user memory（`memory_items` 在 per-agent `agent_state.db`）一致的隔离模型。

### D2 — 删 scope 列，作用域隐式 = 该 agent

`agent_memory_items` 去掉 `scope_type`/`scope_id`；`create/search/list/iter` 去掉 scope 参数；向量命名空间从 `shared:{scope_type}:{scope_id}` 简化为无 scope 维（如固定 `agentmem:` 前缀，由 per-agent 物理库隔离）。
**为何**：per-agent 物理隔离已提供边界，scope 列冗余且无人消费。

### D3 — 全链路正名（不留 shim）

`memory/shared.py`→`agent_memory.py`；`SharedMemoryItem`→`AgentMemoryItem`；`create/search/list/iter_*_shared_memory*`→`*_agent_memory*`；`memory/__init__` 导出改名；`shared_memory_migrations.py`→`agent_memory_migrations.py`；reflection `suggest_shared_memory_or_kb` 动作术语与 `apply_shared_memory_proposal`→`apply_agent_memory_proposal`。
**为何**：半成品、无外部消费者，直接改名净化优于留 shim 包袱。

### D4 — 迁移：重建而非搬迁

嵌入式 forward-only：新建 `agent_memory_items`（无 scope 列）；旧 `shared_memory*` 表/文件丢弃，**不搬数据**（上线前内测窗口，`[[persistence-redesign-roadmap]]` #3 口径）。
**为何**：无生产数据、无消费者，搬迁零收益。

### D5 — agent_memory 物理落点：独立 `agent_memory.db`（暂定）

保持与目标态文档一致：per-agent 独立 `agent_memory.db`（+ 向量），经 `agent_scope`。
**Alt（design open）**：折叠进 `agent_state.db`（少一个文件、与 `memory_items` 同库同 scope）——更简，但偏离已评审文档。倾向先按文档独立，apply 时若发现折叠明显更优再回这条（需同步更新布局文档）。

## Risks / Trade-offs

- **[platform 投影改 per-agent 可能影响 admin 投影调用方]** → `platform-read-projection` 同步改 per-agent 直读；只读不迁移句柄不变。
- **[reflection 动作名变更使旧 proposal 记录失配]** → 重建窗口，旧 proposal 丢弃；无历史包袱。
- **[改名波及 ~10 文件]** → 一次性机械改名 + 护栏（`test_module_dependency_guardrails` 仍绿、`memory ↛ reflection` 仍绿）兜底。
- **[误把"读注入"也做了导致范围膨胀]** → Non-Goals 明确：本片只到"正名 + 重作用域 + 删 scope"，读注入单独立项。

## Migration Plan

1. 嵌入式迁移新版本建 `agent_memory_items`（无 scope）；旧 `shared_memory*` 不保留。
2. 代码全链路改名；删 `tenant_scope.open_shared_memory_db`，加 `agent_scope` 的 agent memory 句柄。
3. platform 投影改 per-agent。
4. 回滚：恢复旧符号/路由即可；无数据搬迁故回滚无数据风险。

## Open Questions

- D5：`agent_memory.db` 独立 vs 折叠进 `agent_state.db`——倾向独立（合文档），apply 时复核。
- `config.py` 是否有 shared-memory 设置项需正名/简化（apply 时确认）。
