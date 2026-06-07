## 1. agent_store 列举所有 agent 名

- [x] 1.1 Write failing test（integration）：`agent_store.list_all_names()` 返回所有 authored agent 名，按名排序
- [x] 1.2 运行确认红：`uv run pytest tests/integration/test_agent_admin_store.py -x -q -k list_all_names`
- [x] 1.3 实现：`agent_store.list_all_names() -> list[str]`，`SELECT name FROM agents ORDER BY name`
- [x] 1.4 运行确认绿：同上命令

## 2. materialize 全量 re-export

- [x] 2.1 Write failing test（integration）：`materialize.rematerialize_all()` 对所有 agent 写 home，返回成功的 agent 名列表
- [x] 2.2 运行确认红：`uv run pytest tests/integration/test_agent_materialize_export.py -x -q -k rematerialize_all`
- [x] 2.3 实现：`materialize.rematerialize_all() -> list[str]`，遍历 `agent_store.list_all_names()` 调 `materialize_from_store(name)`，捕获单个异常记录告警继续
- [x] 2.4 运行确认绿：同上命令

## 3. skill_admin_api 接入触发

- [x] 3.1 Write failing test（unit）：`disable_skill` / `enable_skill` 调用后触发 `materialize.rematerialize_all()`；`set_skill_agent_binding` 调用后触发 `materialize.materialize_from_store(<agent_name>)`（mock materialize，断言调用）
- [x] 3.2 运行确认红：`uv run pytest tests/unit/test_skill_admin_api.py -x -q -k rematerialize`
- [x] 3.3 实现：在 `disable_skill`/`enable_skill` 写审计后调 `_engine_rematerialize_all()` seam；在 `set_skill_agent_binding` 写审计后用 `agent_store.get_agent_name_by_id(int(agent_id))` 解析 name 并调 `materialize_from_store`（解析失败则跳过）。新增可注入 seam 便于测试
- [x] 3.4 运行确认绿：同上命令

## 4. 验证与收尾

- [x] 4.1 运行相关测试：`uv run pytest tests/unit/test_skill_admin_api.py tests/integration/test_agent_materialize_export.py tests/integration/test_agent_admin_store.py -q`
- [x] 4.2 运行全套测试：`uv run pytest -x -q`
- [x] 4.3 运行 lint + 类型检查：`uv run ruff check src tests && uv run mypy src/fleetent/platform/skill_management/skill_admin_api.py src/fleetent/platform/agent_lifecycle/materialize.py src/fleetent/agent_store.py`
- [x] 4.4 运行测试层级检查：`uv run python scripts/check_test_layers.py`
