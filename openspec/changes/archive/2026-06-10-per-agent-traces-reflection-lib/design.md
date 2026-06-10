## Context

3b-2 是 per-agent 库迁移链的第二步（3b-1 已立 `agent_scope` + per-agent 库 + session 首个消费者）。`traces`（`observability/traces.py:154 ensure_schema`，建 `traces` 表）与 `reflection`（`reflection/reflection.py:945 ensure_schema`，建 `reflection_reports` 表）仍 `ensure_schema`-into-global，本切片迁入 per-agent 库。无新设计——照搬 3b-1/KB 的 lift-DDL + 路由套路。

## Goals / Non-Goals

**Goals:** traces + reflection 迁入 per-agent `agent_state.db`（agent_scope + Y）。
**Non-Goals:** memory（3b-3）、approvals（3b-4）、shared（3c）、fan-out（3d）；不改 traces/reflection 的业务行为，仅改 schema 来源与连接。

> **3b-1 落地复核（关键）**：3b-1 把 session 迁移落成 **session 专属列表** `session/migrations.py:MIGRATIONS=[(1, CREATE sessions...)]`，`agent_app._init_agent_db_schema` 调 `agent_scope(...).open_state_db(SESSION_MIGRATIONS)`。但 `migrate()` 以 **`PRAGMA user_version` 为 per-文件 单一版本戳**——`agent_state.db` 现 user_version=1。若 3b-2 给 traces 建**独立** migrations 列表再 `open_state_db` 跑同一文件：traces 从 v1→被跳过（表不建，静默坏）；traces 用 v2→下次 boot 跑 session 列表(只知 v1)即 `SchemaTooNewError` 崩。**两条都炸。**

## Decisions

**D1 `agent_state.db` 由一份「统一 per-agent MIGRATIONS」管，不是每 store 各一份。** 因单文件单 `user_version`。**3b-2 必须把 3b-1 的 session 专属列表合并进统一列表**：新建 per-agent 统一迁移模块（如 `runtime` 或 `session` 邻近的 `agent_state` 迁移），内容 = session(v1) + traces(v2) + reflection(v3) 单调版本；`agent_app` 改为对统一列表**单次** `open_state_db(AGENT_STATE_MIGRATIONS)`。`session/migrations.py` 的步并入该列表（保持 v1 不变以兼容已建库）。
- 备选：每 store 独立列表各跑 `open_state_db`。否决——per-文件 user_version 撞戳 / `SchemaTooNewError`（见上方复核）。
**D2 连接走 `agent_scope`。** 删 traces/reflection 的 `create_database`/`ensure_schema`-into-global 路径。
**D3 ADDED 焦点 requirement,不 re-MODIFY「ensure_schema list」。** 避免与 3b-1/3/4 对同一 requirement 的并发改冲突；旧「Each agent-side store exposes ensure_schema」requirement 在 per-agent 链末（3b-4）统一退役。
**D4 后续 3b-3/3b-4 同样 append 进这份统一 MIGRATIONS**（memory=v4、approvals=v5…），各自切片只追加版本步、不另起列表。

## Risks / Trade-offs

- **append 进 per-agent MIGRATIONS 的版本号需接 3b-1 之后。** → apply 时按 3b-1 落地的 `MIGRATIONS` 实际版本接续；红绿覆盖空库迁移等价性。
- **与 3b-1 的 agent_scope 契约耦合。** → 假设其 propose 契约；apply 前复核。

## Migration Plan

1. lift traces + reflection DDL 进 per-agent `MIGRATIONS`（接 3b-1 之后版本）。
2. 二者连接走 `agent_scope`；删自连接/ensure_schema-into-global；`_init_agent_db_schema` 接线。
3. 回归 + 门禁。回滚 = revert（新库全新建，无数据迁移）。
