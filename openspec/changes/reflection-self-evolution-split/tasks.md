> 前置：阶段1（vector_store）、阶段2（KB retrieval 边界）、阶段4（memory 顶层 + memory.shared 写接口面）已合并。每个实现 task 严格 TDD（红→绿→可选 refactor）。

## 1. 三刀切结构契约 + 护栏（TDD 红先行）

- [x] 1.1 写失败测试：断言 `fleetent.reflection` 顶层包（引擎 + `store`）存在；`governance.reflection_gate` 存在；`platform.reflection_management` 存在（此时不存在 → 红）（`tests/unit/`，import 静态检查）
- [x] 1.2 写失败测试：断言护栏边——`reflection` ✗→ `knowledge_base.ingest`；`reflection` / `governance` ✗→ `fleetent.platform`；`memory` ✗→ `reflection`（启用阶段4 TODO）（此时未拆 → 红）

## 2. 自进化引擎提为顶层 agent（TDD）

- [ ] 2.1 写失败测试：断言 `reflection` 引擎产出 proposal 而不直接执行变更；引擎只读 trace/memory/`knowledge_base.retrieval`
- [ ] 2.2 `git mv reflection.py → reflection/`：引擎（run_*/generate_*/findings/`_read_memory_signals`）+ `reflection/store.py`（proposal/report 表 CRUD、save_report）；引擎内不细分
- [ ] 2.3 旧路径 `intelligence/reflection.py` 留 re-export shim
- [ ] 2.4 跑测试 → 绿

## 3. 变更审批门 → governance（TDD）

- [ ] 3.1 写失败测试：断言 `governance/reflection_gate` 的 `resolve(approve)` 回调对应真相源写接口（user/shared memory→memory.shared 写、skill→skill 库、KB→沉淀源不直接写 KB）；异步不阻塞引擎
- [ ] 3.2 抽 approve/reject/expire/apply + `_apply_maintenance_action`/`_auto_apply_allowed`/`_require_*` 到 `governance/reflection_gate.py`；经 `reflection.store` 改 proposal 状态
- [ ] 3.3 实现 `resolve()` 后回调真相源写（落地逻辑复用原 `apply_*`，仅换调用位置）
- [ ] 3.4 跑测试 → 绿

## 4. 审批渠道按类型路由（TDD）

- [ ] 4.1 写失败测试：断言 user memory proposal 走 IM（agent 自主，不依赖 platform）；skill/KB proposal 走 platform console 暴露面
- [ ] 4.2 门内实现按 proposal 类型路由（user/shared→IM；skill/KB→console）；shared-memory "找对人" 留可注入 resolver 接口（草案，apply 时定具体映射）
- [ ] 4.3 跑测试 → 绿

## 5. 管理 API → platform/reflection_management（TDD）

- [ ] 5.1 写失败测试：断言 `platform/reflection_management` 提供 list/get proposal + 趋势查询，只读 agent 侧 reflection store
- [ ] 5.2 新建 `platform/reflection_management/`；迁 `get/list_*_proposals`、`get_reflection_trend_summary` + `_trend_*`/`_aggregate_*` 到此
- [ ] 5.3 跑测试 → 绿

## 6. 破 memory↔reflection 循环（与阶段4 合并）

- [ ] 6.1 写失败测试：断言 `memory` 不 import `reflection`；shared-memory proposal 落地经门回调 `memory.shared` 写接口
- [ ] 6.2 移除 `memory/shared.py`、`memory/trends.py` 的 lazy-import reflection；`mark_shared_memory_proposal_applied` 迁 `reflection.store`，由门调用；trends 的 proposal 聚合迁 reflection_management
- [ ] 6.3 启用 `memory ✗→ reflection` 护栏（阶段4 标 TODO）
- [ ] 6.4 跑第 1 组护栏测试 → 绿

## 7. skill 评审消费方迁移

- [ ] 7.1 迁 `skill_admin_api.reflection_list_proposals`/`reflection_proposal_diff`/apply 到 `reflection_management`；`skill_management` 评审 inbox 改为消费 reflection_management（行为不变，过渡期可留薄 re-export）
- [ ] 7.2 全仓 grep 确认无残留硬编码 `intelligence.reflection`（shim 除外）
- [ ] 7.3 `uv run pytest -x -q` → 全绿

## 8. 解耦基线验证

- [ ] 8.1 验证 agent 在「无 platform、platform 表不存在」环境下，`fleetent agent run` + 自进化引擎产出 proposal + user-memory IM 审批落地（除 skill/KB 的 console 审批外）正常工作

## 9. 收尾

- [ ] 9.1 `uv run ruff format src tests && uv run ruff check src tests`
- [ ] 9.2 `uv run mypy src`
- [ ] 9.3 `uv run python scripts/check_test_layers.py`
- [ ] 9.4 `uv run pytest -x -q`（全量绿）

> reflection 异步调度（cron）后置（纲领 §9）。shim 删除时机：本 change 末尾或阶段5 统一收口（见 design §Open Questions）。
