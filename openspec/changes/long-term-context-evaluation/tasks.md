## 0. 前置确认

- [ ] 0.1 确认 `long-term-context-foundation` 已完成或已合入当前工作树
- [ ] 0.2 确认本 change 只做 evaluation baseline，不改变默认 runtime 注入策略
- [ ] 0.3 确认默认 evaluation 不调用真实 LLM、embedding、KB connector 或 SaaS
- [ ] 0.4 确认 evaluation 不触碰 `data/`；如未来需要持久化 setup，必须使用 `tmp_path`

## 1. Evaluation fixture schema

- [ ] 1.1 Write failing tests: fixture 必须包含 name、user_id、agent_id、query、available_tokens、memories、knowledge、expected_text、forbidden_text、expected_sources、forbidden_sources
- [ ] 1.2 Write failing tests: 缺失必需字段或 source assertion 格式非法时 fixture validation failure
- [ ] 1.3 Implement: fixture loader / validator
- [ ] 1.4 Verify green: 运行 `uv run pytest tests/evaluation/test_long_term_context_eval.py -x -q`

## 2. Deterministic runner

- [ ] 2.1 Write failing tests: runner patch memory provider 并调用 `build_context()` 验证 expected_text
- [ ] 2.2 Write failing tests: runner patch fake knowledge provider 并验证 expected_sources
- [ ] 2.3 Write failing tests: runner 验证 forbidden_text 和 forbidden_sources 不出现
- [ ] 2.4 Implement: deterministic long-term context evaluation runner
- [ ] 2.5 Verify green: 运行 `uv run pytest tests/evaluation/test_long_term_context_eval.py -x -q`

## 3. Baseline evaluation scenarios

- [ ] 3.1 Write failing tests: memory-only personal preference fixture 必须注入 memory source
- [ ] 3.2 Write failing tests: KB-only factual reference fixture 必须注入 knowledge source
- [ ] 3.3 Write failing tests: combined memory and KB fixture 必须同时注入两类 source
- [ ] 3.4 Write failing tests: insufficient budget fixture 必须省略 forbidden low-priority context
- [ ] 3.5 Implement: baseline fixtures and runner expectations
- [ ] 3.6 Verify green: 运行 `uv run pytest tests/evaluation/test_long_term_context_eval.py -x -q`

## 4. Optional real-provider smoke guard

- [ ] 4.1 Write failing tests: 未设置 `FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT=1` 时真实 provider smoke 被 skip
- [ ] 4.2 Write failing tests: 设置 opt-in 但缺少 provider credentials/config 时真实 provider smoke 被 skip
- [ ] 4.3 Implement: opt-in real-provider smoke guard
- [ ] 4.4 Verify green: 运行 `uv run pytest tests/evaluation/test_long_term_context_eval.py -x -q`

## 5. Docs and final verification

- [ ] 5.1 更新 `docs/capabilities/long-term-ctx.md`
- [ ] 5.2 更新 `docs/capabilities/intelligence-roadmap.md`
- [ ] 5.3 更新 CI quality gate spec，说明 long-term context evaluation 不进入默认 PR gate
- [ ] 5.4 运行 `uv run pytest tests/evaluation/test_long_term_context_eval.py -x -q`
- [ ] 5.5 运行 `uv run ruff format src tests`
- [ ] 5.6 运行 `uv run ruff check src tests`
- [ ] 5.7 运行 `uv run mypy src`
- [ ] 5.8 运行 `uv run pytest -x -q`
- [ ] 5.9 运行 `openspec validate long-term-context-evaluation --strict`
- [ ] 5.10 运行 `git diff --check`
