## Context

3b-2 是 per-agent 库迁移链的第二步（3b-1 已立 `agent_scope` + per-agent 库 + session 首个消费者）。`traces`（`observability/traces.py:154 ensure_schema`，建 `traces` 表）与 `reflection`（`reflection/reflection.py:945 ensure_schema`，建 `reflection_reports` 表）仍 `ensure_schema`-into-global，本切片迁入 per-agent 库。无新设计——照搬 3b-1/KB 的 lift-DDL + 路由套路。

## Goals / Non-Goals

**Goals:** traces + reflection 迁入 per-agent `agent_state.db`（agent_scope + Y）。
**Non-Goals:** memory（3b-3）、approvals（3b-4）、shared（3c）、fan-out（3d）；不改 traces/reflection 的业务行为，仅改 schema 来源与连接。

## Decisions

**D1 DDL 原样 lift 进 per-agent `MIGRATIONS`（追加版本步），不改 schema。** 同 3b-1/KB。
**D2 连接走 `agent_scope`。** 删 traces/reflection 的 `create_database`/`ensure_schema`-into-global 路径。
**D3 ADDED 焦点 requirement,不 re-MODIFY「ensure_schema list」。** 避免与 3b-1/3/4 对同一 requirement 的并发改冲突；旧「Each agent-side store exposes ensure_schema」requirement 在 per-agent 链末（3b-4）统一退役。

## Risks / Trade-offs

- **append 进 per-agent MIGRATIONS 的版本号需接 3b-1 之后。** → apply 时按 3b-1 落地的 `MIGRATIONS` 实际版本接续；红绿覆盖空库迁移等价性。
- **与 3b-1 的 agent_scope 契约耦合。** → 假设其 propose 契约；apply 前复核。

## Migration Plan

1. lift traces + reflection DDL 进 per-agent `MIGRATIONS`（接 3b-1 之后版本）。
2. 二者连接走 `agent_scope`；删自连接/ensure_schema-into-global；`_init_agent_db_schema` 接线。
3. 回归 + 门禁。回滚 = revert（新库全新建，无数据迁移）。
