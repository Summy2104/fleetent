## 1. catalog 预算 + compact fallback

- [x] 1.1 Write failing test（unit）：eligible skill 数超 max_skills 时清单只含前 N 个，且指令前有截断警告含 N/M
- [x] 1.2 Write failing test（unit）：渲染超 max_chars 时切 compact（含 location 不含 description）
- [x] 1.3 Write failing test（unit）：小目录（默认上限）渲染与引入预算前一致（完整格式、无警告）
- [x] 1.4 运行确认红：`uv run pytest tests/unit/test_skill_registry.py -x -q -k "budget or compact or truncat"`
- [x] 1.5 实现：`available_skills_prompt(..., max_skills=150, max_chars=18000)`，按 D2 两级降级（条数截断→字符切 compact→compact 再截），按 D3 置警告
- [x] 1.6 运行确认绿：同上命令

## 2. 验证与收尾

- [x] 2.1 运行 skill registry 全部测试：`uv run pytest tests/unit/test_skill_registry.py -q`
- [x] 2.2 运行全套测试：`uv run pytest -x -q`
- [x] 2.3 运行 lint + 类型检查：`uv run ruff check src tests && uv run mypy src/fleetent/skills/registry.py`
- [x] 2.4 运行测试层级检查：`uv run python scripts/check_test_layers.py`
