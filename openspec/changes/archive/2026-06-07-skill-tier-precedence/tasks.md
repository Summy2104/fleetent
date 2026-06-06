## 1. 层级优先冲突解析

- [x] 1.1 Write failing test（unit）：builtin skill 与同名 user skill 冲突时，索引保留 user 条目（即使 builtin 路径排序靠前）
- [x] 1.2 Write failing test（unit）：冲突告警含 `tier_override=True`（跨层）与 `tier_override=False`（同层）
- [x] 1.3 Write failing test（unit）：同层（两 user）冲突仍按路径排序（既有行为不变）
- [x] 1.4 运行确认红：`uv run pytest tests/unit/test_skill_registry.py -x -q -k "tier or conflict"`
- [x] 1.5 实现：`_scan_dir` 冲突分支按 D1 层级优先（`keep_existing = builtin` 当 tiers 不同，否则路径排序），告警加 `tier_override`
- [x] 1.6 运行确认绿：同上命令

## 2. 验证与收尾

- [x] 2.1 运行 skill registry 全部测试：`uv run pytest tests/unit/test_skill_registry.py -q`
- [x] 2.2 运行全套测试：`uv run pytest -x -q`
- [x] 2.3 运行 lint + 类型检查：`uv run ruff check src tests && uv run mypy src/fleetent/skills/registry.py`
- [x] 2.4 运行测试层级检查：`uv run python scripts/check_test_layers.py`
