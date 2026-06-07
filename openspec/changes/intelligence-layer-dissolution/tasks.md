> 前置：阶段1~4 已合并、调用方全部迁移到顶层路径。

## 1. 依赖护栏（TDD 红先行）

- [ ] 1.1 写护栏测试：断言纲领 §6 禁止边（retrieval✗→ingest；memory/KB✗→long_term_ctx/reflection；组件✗→platform；vector_store✗→业务模块）。此时若有残留违规 import → 红（`tests/unit/`，AST/import 静态检查）
- [ ] 1.2 修残留违规 import → 绿
- [ ] 1.3 （决策）确认护栏工具：自写断言（默认）vs import-linter；若选后者按新依赖流程引入

## 2. 删除 shim 与 intelligence 目录

- [ ] 2.1 写失败测试：断言全仓无 `fleetent.intelligence.*` import、`src/fleetent/intelligence/` 不存在（此时 shim 还在 → 红）
- [ ] 2.2 全仓 grep 确认无调用方依赖各过渡 shim
- [ ] 2.3 删除各阶段过渡 re-export shim
- [ ] 2.4 删除空的 `src/fleetent/intelligence/` 目录
- [ ] 2.5 跑第 2 组测试 → 绿

## 3. CLAUDE.md 契约更新（纲领 §8 六条，同 PR）

- [ ] 3.1 架构目录树：移除 `intelligence/` 节点，平铺 vector_store/knowledge_base/memory/reflection/long_term_ctx 为顶层条目
- [ ] 3.2 重新定位组件：KB=独立组件、vector_store=基础设施，不再属"agent 运行时模块"列表
- [ ] 3.3 Forbidden Patterns：写明 KB 读写边界（retrieval✗→ingest）+ 组件✗→platform
- [ ] 3.4 记录三条判据（§2）作为归属判断标准
- [ ] 3.5 写明自进化的写经统一审批门（governance）+ KB agent 自主写入口子
- [ ] 3.6 更新「现存待审计的 agent→platform 依赖」条目（knowledge_base/config 等已清理）

## 4. 收尾验证

- [ ] 4.1 `uv run ruff format src tests && uv run ruff check src tests`
- [ ] 4.2 `uv run mypy src`
- [ ] 4.3 `uv run python scripts/check_test_layers.py`
- [ ] 4.4 `uv run pytest -x -q`（全量绿）
- [ ] 4.5 解耦基线：`fleetent agent run` 在无 platform 环境正常对话 + 检索 + 记忆
