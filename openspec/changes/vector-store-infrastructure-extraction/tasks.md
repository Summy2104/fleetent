## 1. 依赖契约断言（TDD 红先行）

- [ ] 1.1 写失败测试：断言 `fleetent.vector_store` 包可导入、且不 import `fleetent.platform` / `fleetent.intelligence` / `knowledge_base` / `memory`（此时顶层包不存在 → 红）（`tests/unit/`，纯 import 静态检查）
- [ ] 1.2 写失败测试：断言 `fleetent.vector_store` 暴露原 15 个公共符号（search/upsert/delete/reindex/namespace helpers/rerank…）

## 2. 物理移动 + shim

- [ ] 2.1 `git mv src/fleetent/intelligence/vector_store/ src/fleetent/vector_store/`（6 文件整体，保留历史）
- [ ] 2.2 修正 `vector_store/` 内部相对/绝对 import 到新路径
- [ ] 2.3 在 `intelligence/vector_store/__init__.py` 留 re-export shim（`from fleetent.vector_store import *` + 显式 `__all__`）
- [ ] 2.4 跑第 1 组断言测试 → 绿

## 3. 调用方迁移（9 处）

- [ ] 3.1 写失败测试/回归保护：迁移前先确认相关模块现有测试全绿（基线）
- [ ] 3.2 迁移 `knowledge_base/{config,runtime}` 的 import 到 `fleetent.vector_store`
- [ ] 3.3 迁移 `memory/{extraction,maintenance,operations,search,shared}` 的 import
- [ ] 3.4 迁移 `runtime/agent_app`、`agent_config` 的 import
- [ ] 3.5 全仓 grep 确认无残留硬编码 `intelligence.vector_store`（shim 除外）
- [ ] 3.6 跑 `uv run pytest -x -q` → 全绿

## 4. 解耦基线验证

- [ ] 4.1 验证 agent 在「无 platform、platform 表不存在」环境下，依赖 vector_store 的检索/记忆功能正常（`fleetent agent run` smoke 或等价集成测试）

## 5. 收尾

- [ ] 5.1 `uv run ruff format src tests && uv run ruff check src tests`
- [ ] 5.2 `uv run mypy src`
- [ ] 5.3 `uv run python scripts/check_test_layers.py`
- [ ] 5.4 `uv run pytest -x -q`（全量绿）

> shim 删除时机：本 change 末尾或阶段5 统一收口（见 design §Open Questions）。
