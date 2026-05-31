## 0. 前置确认

- [ ] 0.1 确认 `memory-update-merge-actions` 已完成或已合入当前工作树
- [ ] 0.2 确认 evaluation tests 放在 `tests/evaluation/`，不向 `tests/` 根目录新增测试
- [ ] 0.3 确认默认 evaluation 使用 mock LLM，不调用真实外部模型
- [ ] 0.4 确认测试使用 tmp SQLite DB，不触碰 `data/`

## 1. Evaluation fixture 格式

- [ ] 1.1 Write failing tests: evaluation fixture 必须包含 name、initial_memories、conversation、expected_actions、forbidden_actions、mock_actions
- [ ] 1.2 Write failing tests: 缺失必需字段或 action 类型非法时 fixture validation 失败
- [ ] 1.3 实现 fixture loader / validator
- [ ] 1.4 运行 `uv run pytest tests/evaluation -x -q`，确认 1.1/1.2 红测转绿

## 2. Mock LLM deterministic evaluation

- [ ] 2.1 Write failing tests: mock_actions 驱动 `extract_and_update()`，可断言 expected_actions 对应的最终 memory 状态
- [ ] 2.2 Write failing tests: forbidden_actions 不应出现在最终 memory 状态中
- [ ] 2.3 Write failing tests: evaluation runner 隔离 model_router、vector_store 和 SQLite
- [ ] 2.4 实现 mock LLM evaluation runner
- [ ] 2.5 运行 `uv run pytest tests/evaluation -x -q`，确认 2.1-2.3 红测转绿

## 3. 第一批 evaluation 场景

- [ ] 3.1 新增 identity create fixture
- [ ] 3.2 新增 identity update fixture
- [ ] 3.3 新增 context update + TTL refresh fixture
- [ ] 3.4 新增 preferences create fixture
- [ ] 3.5 新增 one-off preference request ignore fixture
- [ ] 3.6 新增 explicit forget / delete fixture
- [ ] 3.7 新增 noisy or invalid conversation ignore fixture
- [ ] 3.8 运行 `uv run pytest tests/evaluation -x -q`，确认全部场景通过

## 4. Optional real LLM evaluation

- [ ] 4.1 Write failing tests: 未设置 `FLEETENT_EVAL_REAL_LLM=1` 时真实 LLM evaluation 被 skip
- [ ] 4.2 Write failing tests: 设置 `FLEETENT_EVAL_REAL_LLM=1` 时 runner 使用真实 `memory_extraction` 路由
- [ ] 4.3 实现真实 LLM evaluation 手动入口，默认不进入 PR gate
- [ ] 4.4 运行 `uv run pytest tests/evaluation -x -q`，确认默认 mock evaluation 稳定通过且真实 LLM case 被 skip

## 5. 文档与收尾验证

- [ ] 5.1 更新 `docs/capabilities/memory.md`，说明 memory extraction evaluation 的默认 mock 与手动真实 LLM 模式
- [ ] 5.2 运行 `uv run pytest tests/evaluation -x -q`
- [ ] 5.3 运行 `uv run pytest -x -q`
- [ ] 5.4 运行 `uv run ruff format src tests`
- [ ] 5.5 运行 `uv run ruff check src tests`
- [ ] 5.6 运行 `uv run mypy src`
- [ ] 5.7 运行 `openspec validate memory-extraction-evaluation`
