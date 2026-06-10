## Context

3b-4 是 per-agent 迁移链末步。现状：`approval_store.ensure_schema(db_path)` 建 `approvals` 表（change A 落地 agent 侧写）；但 alembic 仍有 approvals 孤立定义（060_fix_approvals_id_to_text 等）= 双权威残留。R1 定 agent 侧全权写、platform 只读投影。

## Goals / Non-Goals

**Goals:** approvals + allowlist 迁 per-agent `agent_state.db`（agent_scope+Y）；drop alembic approvals 孤立定义（agent 侧唯一真相源）；退役旧 ensure_schema-list 要求。
**Non-Goals:** platform 只读投影**实现**（依赖 3d 只读 router，本切片只立真相源）；fan-out（3d）。

## Decisions

**D1 agent 侧 approval_store = 唯一真相源,drop alembic approvals 定义。** 兑现 R1 + 双权威收口。
- 备选：留 alembic 定义。否决——双权威漂移源，change A 后它已是孤儿。

**D2 DDL lift + 连接走 agent_scope；管理库 drop 走 alembic 迁移。** 双 schema 权威各按其规则（agent 侧 Y / 管理库 alembic）。

**D3 投影实现延后 3d。** §7 只读投影需"只读 router"（3d 提供）；本切片只确保 approvals 在 per-agent 库、platform 将来能只读它。

**D4 链末 REMOVE「Each agent-side store exposes ensure_schema」。** 至此所有 agent 侧 store 迁 Y，该过渡要求退役。

## Risks / Trade-offs

- **drop alembic approvals 表误删活数据?** → change A 后写侧已在 agent 侧；alembic 表是孤儿；drop 前测试断言管理库无活 approvals 写入路径。
- **approval_store.ensure_schema 签名是 db_path 非 db。** → 迁移时统一为经 agent_scope 取连接，注意改调用点。
- **与 3b-1 agent_scope 契约耦合 + 与 3d 投影衔接。** → apply 前复核 3b-1；投影 stub 留 3d。

## Migration Plan

1. lift approvals + allowlist DDL 进 per-agent MIGRATIONS；连接走 agent_scope。
2. 新增 alembic 迁移 drop 管理库 approvals 定义。
3. agent_app 接线；REMOVE 旧 ensure_schema-list 要求。
4. 回归 + 门禁。回滚 = revert（新库全新建 + 反向迁移）。
