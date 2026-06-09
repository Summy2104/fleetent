> 本变更是 chore 性质的删除,无行为变更。纪律:删除后既有测试**保持全绿**;迁移须**可逆往返**通过;删死代码前**二次 grep 确认零引用**。

## 1. 删除 askit 任务队列三表(Alembic down 迁移)

- [x] 1.1 二次核实:`grep -rn "askit_tasks\|askit_task_logs\|askit_workspaces" src tests`(排除 .pyc)确认**零 .py/测试引用**;确认 `platform/askit_console/agent_apply_api.py` 不碰这三表。
- [x] 1.2 写迁移测试(`tests/integration/`):空库 `alembic upgrade head` 后断言 schema **不含** `askit_tasks`/`askit_task_logs`/`askit_workspaces`(对应 spec scenario)。先见红(当前 head 含这三表)。
- [x] 1.3 新增 Alembic 迁移(append-only,不改 025):`upgrade()` drop 三表;`downgrade()` 按 025 列定义重建。见绿。
- [x] 1.4 迁移可逆性:空库 `upgrade head` → `downgrade -1` → `upgrade head` 往返干净通过。
- [x] 1.5 删除孤儿 `src/fleetent/__pycache__/askit_task_store.cpython-312.pyc`(确认无对应 .py 源)。

## 2. 删除 KB binding 死导出

- [x] 2.1 二次核实:`grep -rn "bind_agent_to_kb\|unbind_agent_from_kb" src tests`,确认公开导出**无生产调用点**(若仅有"测这俩死函数"的测试,一并清理)。
- [x] 2.2 从 `src/fleetent/knowledge_base/__init__.py`(及 `bindings.py` 若适用)移除 `bind_agent_to_kb`/`unbind_agent_from_kb` 的公开导出与实现。
- [x] 2.3 跑 KB 相关单测确认无新增失败(`uv run pytest tests/unit -q -k "knowledge or binding or kb"`)。

## 3. KB binding 读取去重(scope.py ← bindings.py)

- [x] 3.1 核实 `retrieval/scope.py` 与 `bindings.py` 的 binding 读取函数确为重复实现(逐字/等价)。
- [x] 3.2 收敛:`scope.py` 删除重复实现,改 import/复用 `bindings.py` 的单一来源;行为不变。
- [x] 3.3 跑 retrieval/scope 相关测试(integration + unit)确认 binding 解析行为逐字一致、无新增失败。

## 4. 收尾验证

- [x] 4.1 `make test-pr` 全绿(unit〔除 quarantine〕+ 层边界 + 改动文件 ruff)。
- [x] 4.2 `uv run pytest tests/integration -q` 对照 main 基线**无新增失败**。
- [x] 4.3 `openspec validate dead-schema-cleanup` 通过。
- [x] 4.4 复核:未触及 `connectors.agent_id` / `users.api_key`(二者明确不在本次范围)。
