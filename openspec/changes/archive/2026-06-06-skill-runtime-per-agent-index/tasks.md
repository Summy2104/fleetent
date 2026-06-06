## 1. boot 从 home/skills 构建 skill 索引

- [x] 1.1 Write failing test（integration）：boot 一个 home（其 `skills/<skill>/SKILL.md` 存在）后，`skill_registry._index` 含该 skill（mock 掉 IM/infra，只验证 skill 索引来源）
- [x] 1.2 Write failing test（integration）：home 无 `skills/` 时 boot 不抛异常，索引不含该 home 专属 skill
- [x] 1.3 运行确认红：`uv run pytest tests/integration/test_agent_runtime_app.py -x -q -k skill`
- [x] 1.4 实现：`agent_app.boot()` 把 `scan_skills()` 改为 `scan_skills(skills_dir=str(home_dir / "skills"))`
- [x] 1.5 运行确认绿：同上命令

## 2. 验证与收尾

- [x] 2.1 运行 agent runtime 相关测试：`uv run pytest tests/integration/test_agent_runtime_app.py tests/integration/test_single_agent_runtime.py -q`
- [x] 2.2 运行全套测试：`uv run pytest -x -q`
- [x] 2.3 运行 lint + 类型检查：`uv run ruff check src tests && uv run mypy src/fleetent/runtime/agent_app.py`
- [x] 2.4 运行测试层级检查：`uv run python scripts/check_test_layers.py`
