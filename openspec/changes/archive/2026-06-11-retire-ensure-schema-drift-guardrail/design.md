## Context

漂移护栏（`agent-db-schema-self-init` 的「ensure_schema 与 alembic 一致」）是 #1 时期为「agent 表混在 `fleetent.db`、alembic 与 ensure_schema 双定义」立的过渡件。#3 把 agent 表迁入 per-agent `agent_state.db`（Y）后，approvals 已由 073 forward-drop 出 alembic，但 `traces` / `memory_items` / `reflection_reports` 漏做：

- `grep op.drop_table`：drop 迁移（063-073）覆盖 monitoring/askit/quota/invites/scheduled_tasks/kb_bindings/approvals，**无** traces/memory/reflection 的 forward-drop（只有 003/004/005 自己的 downgrade）。
- 故 alembic head 仍建这三表（管理库孤儿空表），且 `traces.ensure_schema` / `reflection.ensure_schema` 仅被护栏测试 `test_schema_drift_guard.py` 调用而存活；`knowledge_base/operations.ensure_schema` 已彻底无调用方（KB 迁 Y + 被护栏排除）。

`schedule_store.ensure_schema`（`scheduled_tasks`）不同：071 已 drop 它出 alembic，schedule_store 经 db.py 自建之——它是管理侧 self-init、非本护栏对象，保留。

## Goals / Non-Goals

**Goals:**
- forward-drop `traces` / `memory_items` / `reflection_reports` 出 alembic，结束双定义。
- 退役漂移护栏 requirement + 删护栏测试。
- 删三处随之变死的 `ensure_schema`。

**Non-Goals:**
- 动 `schedule_store.ensure_schema`（live 自建，保留）。
- 动这三表的 agent 侧 Y 定义（不变，仍唯一真相源）。
- KB 图谱表 lift（#2）/ kb_reflection_reports（#4）——另议，不在本 change。

## Decisions

### D1：forward-drop 镜像 073（approvals）
新增一条 alembic 迁移，`upgrade()` drop 三表、`downgrade()` 按 003/004/005 原定义重建（空表）。**为何**：与 approvals 的 073 一致、可回滚；被 drop 的是管理库永不被写的空孤儿表（#3 后读写全经 agent_scope），无数据风险。

### D2：先退役护栏测试，再删 ensure_schema
顺序：① 加 drop 迁移 → ② 删 `test_schema_drift_guard.py`（它是唯一调用 traces/reflection ensure_schema 的地方）→ ③ 删三个 `ensure_schema()`。**为何**：删测试前先删函数会让测试 import 失败误报；按依赖序走。

### D3：调整 test_traces_reflection_agent_scope.py
该测试守卫「agent_app 不调用 traces.ensure_schema / reflection.ensure_schema」。函数移除后该守卫退化为恒真——改为校验「schema 由统一 MIGRATIONS 建」或直接移除冗余用例（保留其仍有意义的部分，如 agent_scope 路由断言）。**为何**：守卫的对象消失，应转为校验正向不变量而非"不调用已不存在的函数"。

## Risks / Trade-offs

- [drop 迁移误删仍被写的表] → 已确认 #3 后 traces/memory/reflection 读写全经 agent_scope→agent_state.db；管理库副本是空孤儿。drop 前可加断言/人工确认管理库该表为空。
- [其它测试隐式依赖管理库有这三表] → `make test-pr` + 全量 integration 对照基线；逐个修依赖管理库 schema 的测试。
- [漂移护栏退役后，未来再加双定义无人发现] → 退役是对的（已无双定义场景）；将来若再引入 dual-authority，应在该 change 内自带校验，而非长期养一个空跑护栏。

## Migration Plan

1. 加 alembic forward-drop 迁移（drop 三表，downgrade 重建）。
2. 删 `test_schema_drift_guard.py`；调整 `test_traces_reflection_agent_scope.py`。
3. 删 `traces.ensure_schema` / `reflection.ensure_schema` / `operations.ensure_schema`。
4. 退役 spec requirement（本 change 的 delta）。
5. 回滚：alembic downgrade 重建三空表；恢复函数与测试（git）。

## Open Questions

- 无。
