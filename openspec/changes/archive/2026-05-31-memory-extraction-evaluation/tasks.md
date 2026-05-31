## 0. 前置确认

- [x] 0.1 确认 `memory-update-merge-actions` 已完成或已合入当前工作树
- [x] 0.2 确认 evaluation tests 放在 `tests/evaluation/`，不向 `tests/` 根目录新增测试
- [x] 0.3 确认默认 evaluation 使用 mock LLM，不调用真实外部模型
- [x] 0.4 确认测试使用 tmp SQLite DB，不触碰 `data/`

## 1. Evaluation fixture 格式

- [x] 1.1 Write failing tests: evaluation fixture 必须包含 name、initial_memories、conversation、mock_actions、expected_memories、forbidden_memories
- [x] 1.2 Write failing tests: 缺失必需字段或 action 类型非法时 fixture validation 失败
- [x] 1.3 实现 fixture loader / validator
- [x] 1.4 运行 `uv run pytest tests/evaluation -x -q`，确认 1.1/1.2 红测转绿

## 2. Mock LLM deterministic evaluation

- [x] 2.1 Write failing tests: mock_actions 驱动 `extract_and_update()`，可断言 expected_memories 对应的最终 memory 状态
- [x] 2.2 Write failing tests: forbidden_memories 不应出现在最终 memory 状态中
- [x] 2.3 Write failing tests: evaluation runner 隔离 model_router、vector_store 和 SQLite
- [x] 2.4 实现 mock LLM evaluation runner
- [x] 2.5 运行 `uv run pytest tests/evaluation -x -q`，确认 2.1-2.3 红测转绿

## 3. 第一批 evaluation 场景

- [x] 3.1 新增 identity create fixture
- [x] 3.2 新增 identity update fixture
- [x] 3.3 新增 context update + TTL refresh fixture
- [x] 3.4 新增 preferences create fixture
- [x] 3.5 新增 one-off preference request ignore fixture
- [x] 3.6 新增 explicit forget / delete fixture
- [x] 3.7 新增 noisy or invalid conversation ignore fixture
- [x] 3.8 运行 `uv run pytest tests/evaluation -x -q`，确认全部场景通过

## 4. Optional real LLM evaluation

- [x] 4.1 Write failing tests: 未设置 `FLEETENT_EVAL_REAL_LLM=1` 时真实 LLM evaluation 被 skip
- [x] 4.2 Write failing tests: 设置 `FLEETENT_EVAL_REAL_LLM=1` 时 runner 使用真实 `memory_extraction` 路由
- [x] 4.3 Write failing tests: 设置 `FLEETENT_EVAL_REAL_LLM=1` 但缺少 provider API key 时真实 LLM evaluation 被 skip
- [x] 4.4 实现真实 LLM evaluation 手动入口，默认不进入 PR gate
- [x] 4.5 运行 `uv run pytest tests/evaluation -x -q`，确认默认 mock evaluation 稳定通过且真实 LLM case 被 skip

## 5. 文档与收尾验证

- [x] 5.1 替换 `tests/evaluation/test_placeholder.py`，不保留无意义 placeholder
- [x] 5.2 更新 `docs/capabilities/memory.md`，说明 memory extraction evaluation 的默认 mock 与手动真实 LLM 模式
- [x] 5.3 运行 `uv run pytest tests/evaluation -x -q`
- [x] 5.4 运行 `uv run pytest -x -q`
- [x] 5.5 运行 `uv run ruff format src tests`
- [x] 5.6 运行 `uv run ruff check src tests`
- [x] 5.7 运行 `uv run mypy src`
- [x] 5.8 运行 `openspec validate memory-extraction-evaluation`
