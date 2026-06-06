## 1. write_home 复制 skill 文件到 agent home

- [x] 1.1 Write failing test（integration）：全局 skills 目录含一个 skill 时，`write_home()` 后 `<home>/skills/<skill>/SKILL.md` 存在且内容一致
- [x] 1.2 Write failing test（integration）：源 skills 目录不存在时 `write_home()` 不抛异常，正常返回 home
- [x] 1.3 Write failing test（integration）：连续两次 `write_home()` 幂等，不因目录已存在报错
- [x] 1.4 运行确认红：`uv run pytest tests/integration/test_agent_materialize_export.py -x -q -k skills`
- [x] 1.5 实现：在 `write_home()` 的 `_seed_env` 之后新增 `_copy_skills(home)` helper：`src = Path(skill_registry._resolve_skills_dir(None))`，`if src.exists(): shutil.copytree(src, home/"skills", dirs_exist_ok=True)`，捕获异常记录告警；顶部加 `import shutil` 和 `from fleetent.skills import registry as skill_registry`
- [x] 1.6 运行确认绿：同上命令

## 2. 验证与收尾

- [x] 2.1 运行 materialize 相关 integration 测试：`uv run pytest tests/integration/test_agent_materialize_export.py -x -q`
- [x] 2.2 运行全套测试：`uv run pytest -x -q`
- [x] 2.3 运行 lint + 类型检查：`uv run ruff check src tests && uv run mypy src/fleetent/platform/agent_lifecycle/materialize.py`
- [x] 2.4 运行测试层级检查：`uv run python scripts/check_test_layers.py`
