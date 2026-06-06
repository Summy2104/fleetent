## 1. disabled_skills 来自全局 disable 状态

- [x] 1.1 Write failing test（integration，真实 DB）：某 skill `global_enabled=0` 时，`agent_file_from_store()` 产出的 `AgentFile.disabled_skills` 包含该 skill 名
- [x] 1.2 运行确认红：`uv run pytest tests/integration/test_agent_home_materialize.py -x -q -k disabled`
- [x] 1.3 实现：在 `agent_file_from_store()` 新增 `_global_disabled_skills()` helper，读 `skill_admin_store.list_states()` 筛 `global_enabled=0`，捕获缺表异常回退空列表；把结果传入 `AgentFile(disabled_skills=...)`
- [x] 1.4 运行确认绿：同上命令

## 2. allowed_skills 来自 agent_skills 绑定

- [x] 2.1 Write failing test（integration）：agent 有绑定行时 `allowed_skills` 取 enabled=1 子集；无绑定行时回退 authored 值；绑定全关时为空
- [x] 2.2 运行确认红：`uv run pytest tests/integration/test_agent_home_materialize.py -x -q -k allowed`
- [x] 2.3 实现：在 `agent_file_from_store()` 新增 `_allowed_skills_for(agent)` helper，用 `has_any_binding(str(agent.id))` 判定：有绑定→`sorted(enabled_skill_names(str(agent.id)))`，无绑定→`agent.allowed_skills`；捕获缺表异常回退 authored 值
- [x] 2.4 运行确认绿：同上命令

## 3. 验证与收尾

- [x] 3.1 运行 materialize 相关 integration 测试：`uv run pytest tests/integration/test_agent_home_materialize.py -x -q`
- [x] 3.2 运行全套测试：`uv run pytest -x -q`
- [x] 3.3 运行 lint + 类型检查：`uv run ruff check src tests && uv run mypy src/fleetent/platform/agent_lifecycle/materialize.py`
- [x] 3.4 运行测试层级检查：`uv run python scripts/check_test_layers.py`
