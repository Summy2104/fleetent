> 前置：阶段1（vector_store 顶层）、阶段2（KB retrieval 边界）已合并。每个实现 task 严格 TDD（红→绿→可选 refactor）。本阶段在阶段3 前实施。

## 1. 顶层化结构契约 + 护栏（TDD 红先行）

- [x] 1.1 写失败测试：断言 `fleetent.memory` / `fleetent.long_term_ctx` 顶层包存在且公共符号齐（此时不存在 → 红）（`tests/unit/`，import 静态检查）
- [x] 1.2 写失败测试：断言护栏边——`memory` ✗→ `long_term_ctx`；`memory` / `long_term_ctx` ✗→ `fleetent.platform`（此时未迁 → 红）

## 2. memory 提为顶层（TDD）

- [x] 2.1 `git mv src/fleetent/intelligence/memory/ src/fleetent/memory/`；修内部相对/绝对 import 到顶层
- [x] 2.2 旧路径 `intelligence/memory/__init__.py` 留 re-export shim（旧公共符号全可达）
- [x] 2.3 跑第 1 组 memory 断言 → 绿（memory 顶层可导入、护栏 memory✗→platform 绿）

## 3. long_term_ctx 提为独立顶层包（TDD）

- [ ] 3.1 写失败测试：断言 `long_term_ctx` 是独立顶层包（含 `_policy`）、不是 runtime 子模块；runtime → long_term_ctx 单向
- [ ] 3.2 `git mv` `long_term_ctx.py` → `long_term_ctx/__init__.py`、`long_term_ctx_policy.py` → `long_term_ctx/_policy.py`；修内部 import；旧路径留 shim
- [ ] 3.3 跑测试 → 绿

## 4. shared-memory 审计薄壳归 platform（TDD）

- [x] 4.1 写失败测试：断言 `record_shared_memory_admin_audit` 审计写经 platform 薄壳完成，agent 侧 memory.shared 能力本体（create/update/archive/search/apply）不依赖 platform
- [x] 4.2 把审计记录迁到 platform 薄壳；`admin_cli/shared_memory.py` 调整为经薄壳记录审计、经 agent 侧核心写
- [x] 4.3 跑测试 → 绿

## 5. 调用方迁移 + 循环铺路

- [ ] 5.1 迁 `runtime/loop`（memory extraction + long_term_ctx 构建上下文）→ 顶层 `memory` / `long_term_ctx`
- [ ] 5.2 迁 `agent_config`（long_term_ctx_policy）→ `long_term_ctx._policy`
- [ ] 5.3 保留 `memory/shared.py`、`memory/trends.py` 的 lazy-import reflection（经 shim 可用）；在测试/注释标注 `memory ✗→ reflection` 护栏 TODO（阶段3 门落地后启用）
- [ ] 5.4 全仓 grep 确认无残留硬编码 `intelligence.memory` / `intelligence.long_term_ctx`（shim 除外）
- [ ] 5.5 跑第 1 组护栏测试 → 绿

## 6. 解耦基线验证

- [ ] 6.1 验证 agent 在「无 platform、platform 表不存在」环境下，`fleetent agent run` 对话 + 记忆提取/检索 + long_term_ctx 注入正常工作（集成测试或 smoke）

## 7. 收尾

- [ ] 7.1 `uv run ruff format src tests && uv run ruff check src tests`
- [ ] 7.2 `uv run mypy src`
- [ ] 7.3 `uv run python scripts/check_test_layers.py`
- [ ] 7.4 `uv run pytest -x -q`（全量绿）

> `memory ✗→ reflection` 的护栏在阶段3（governance 审批门居中破环）启用。shim 删除时机：本 change 末尾或阶段5 统一收口（见 design §Open Questions）。
