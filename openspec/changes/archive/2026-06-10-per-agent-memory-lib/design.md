## Context

3b-3 迁 memory 进 per-agent 库 + 落 R2-叉2（去 namespace）。现状：`memory/store.py` `ensure_schema` 建 `memory_items`（含 `namespace` 列）；`vector_store.memory_namespace(user_id, namespace="default")` 有 vestigial 第二参（多数 spec 已写 `mem:{user_id}` 单参形态——code 落后于 spec）；memory `search`/`extract` 带 `namespace` 参。

## Goals / Non-Goals

**Goals:** memory → per-agent `agent_state.db`（agent_scope+Y）；移除 namespace 第二参，agent 隔离靠 per-agent 物理库。
**Non-Goals:** shared memory（3c，仍用 `shared:`）；traces/reflection（3b-2）；approvals（3b-4）；fan-out（3d）。不改 user-scoping 语义。

## Decisions

**D1 agent 隔离 = per-agent 物理库,不是 namespace 列（R2-叉2）。** 删 `memory_items.namespace` 列 + `memory_namespace`/操作的第二参。新库全新建即无该列，无搬迁键难题。
- 备选：保留 namespace 列做逻辑隔离。否决——既已 per-agent 物理分库，namespace 冗余；删之简化向量串与 API。

**D2 memory_items DDL（去 namespace 列）append 进统一列表 `runtime/agent_state_migrations.py`（3b-2 建立）+ 连接走 agent_scope。** 版本号**接该列表当前 max 之后**（3b-2 落地后 sessions/traces/reflection 已用到 v5~v6 量级，**勿硬编 v4**——按实际 max 追加）；**不另起独立 MIGRATIONS 列表**（单文件单 user_version）。

**D3 ADDED 焦点 requirement,不 re-MODIFY「ensure_schema list」。** 同 3b-2，避免并发改冲突。

**D4 顺带清 3b-2 遗留死码。** 3b-2 把 sessions DDL inline 进了统一列表，但旧 `session/migrations.py`（及其测试 `test_session_agent_migrations.py`）未删、已成孤儿。本切片删 `session/migrations.py`、重指向或删该测试（指向 `agent_state_migrations`）。

## Risks / Trade-offs

- **去 namespace 第二参的调用点 ripple**（memory_namespace / search / extract + 调用方）。→ 全仓 grep 调用点；红绿覆盖；spec 多数已是单参形态，改的是 code 对齐。
- **与 3b-1 agent_scope 契约耦合。** → apply 前复核。

## Migration Plan

1. lift `memory_items` DDL（去 namespace 列）进 per-agent MIGRATIONS。
2. 连接走 agent_scope；`_init_agent_db_schema` 接线。
3. 去 `memory_namespace` 第二参 + memory `search`/`extract_and_update` 的 `namespace` 参 + 调用点。
4. 回归 + 门禁。回滚 = revert（新库全新建）。
