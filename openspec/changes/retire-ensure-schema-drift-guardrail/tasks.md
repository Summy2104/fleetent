## 1. forward-drop 三张孤儿表出 alembic

- [ ] 1.1 写测试（integration）：全新管理库 `alembic upgrade head` 后不含 `traces` / `memory_items` / `reflection_reports`（迁移前见红——当前 head 仍建这三表） —— 见红
- [ ] 1.2 新增 alembic 迁移（接当前 head，如 074_*）：`upgrade()` drop `traces` / `memory_items` / `reflection_reports`；`downgrade()` 按 003/004/005 原列定义重建空表（镜像 073 approvals） —— 见绿
- [ ] 1.3 写测试（integration）：迁移后某 agent 的 `agent_state.db`（Y）仍含这三表、读写经 agent_scope 正常 —— 见红→见绿

## 2. 退役漂移护栏测试 + 调整守卫测试

- [ ] 2.1 删除 `tests/integration/test_schema_drift_guard.py`（护栏退役，唯一调用 traces/reflection ensure_schema 处）
- [ ] 2.2 调整 `tests/integration/test_traces_reflection_agent_scope.py`：移除「agent_app 不调用 traces/reflection.ensure_schema」这类对象已消失的守卫；保留/改写为「schema 由统一 MIGRATIONS 建 + agent_scope 路由」正向断言 —— 跑该文件确认绿

## 3. 删随之变死的 ensure_schema

- [ ] 3.1 grep 全仓确认 `traces.ensure_schema` / `reflection.ensure_schema` / `operations.ensure_schema` 无生产 + 无测试调用方（2.1/2.2 后）
- [ ] 3.2 删 `observability/traces.py` 的 `ensure_schema()`
- [ ] 3.3 删 `reflection/reflection.py` 的 `ensure_schema()`
- [ ] 3.4 删 `knowledge_base/operations.py` 的 `ensure_schema()`（若 `__init__` re-export 它则一并清）
- [ ] 3.5 grep 自查：`def ensure_schema` 仅余 `schedule_store`（live 自建，保留）

## 4. 收尾

- [ ] 4.1 验证基线：无 platform、管理库表不存在下 `fleetent agent run` 仍正常（schema 来自 Y）；`alembic upgrade head` 的管理库不含三表
- [ ] 4.2 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q`（对照 main 基线，无新增失败）
