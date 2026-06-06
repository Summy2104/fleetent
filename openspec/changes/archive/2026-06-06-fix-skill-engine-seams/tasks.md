## 1. 修复 engine_reload — 原子切换

- [x] 1.1 Write failing test：`engine_reload()` 调用 `skill_registry.reload()` 而非 `skill_registry.scan()`（在 `tests/unit/test_skill_admin_api.py` 中 mock 两个函数，断言 `reload` 被调用、`scan` 未被调用）
- [x] 1.2 运行测试确认红：`uv run pytest tests/unit/test_skill_admin_api.py -x -q -k reload`
- [x] 1.3 实现：将 `skill_admin_api.py:engine_reload()` 中的 `skill_registry.scan()` 替换为 `skill_registry.reload()`
- [x] 1.4 运行测试确认绿：`uv run pytest tests/unit/test_skill_admin_api.py -x -q -k reload`

## 2. 修复 engine_audit — 真实注入审计

- [x] 2.1 Write failing test：`engine_audit(content)` 调用 `skill_audit.audit(content)` 并返回其结果（mock `skill_audit.audit`，断言被调用且返回值透传）
- [x] 2.2 运行测试确认红：`uv run pytest tests/unit/test_skill_admin_api.py -x -q -k audit`
- [x] 2.3 实现：将 `skill_admin_api.py:engine_audit()` 的 stub 替换为 `from fleetent.skills import audit as skill_audit; return skill_audit.audit(content)`
- [x] 2.4 运行测试确认绿：`uv run pytest tests/unit/test_skill_admin_api.py -x -q -k audit`

## 3. 验证与收尾

- [x] 3.1 运行相关单元测试全套：`uv run pytest tests/unit/test_skill_admin_api.py -x -q`
- [x] 3.2 运行全套测试：`uv run pytest -x -q`
- [x] 3.3 运行测试层级检查：`uv run python scripts/check_test_layers.py`
