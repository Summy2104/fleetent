## 0. 前置确认

- [x] 0.1 确认 `reflection-foundation` 已完成或已合入当前工作树
- [x] 0.2 确认本 change 只做 report evaluation baseline，不做 finding 自动应用
- [x] 0.3 确认默认 evaluation 不调用真实 LLM、embedding、KB connector 或 SaaS
- [x] 0.4 确认 evaluation 使用 tmp SQLite，不触碰 `data/`

## 1. Evaluation fixture schema

- [x] 1.1 Write failing tests: fixture 必须包含 name、scope、trace_events、memory_signals、expected_findings、forbidden_findings、forbidden_persisted_text
- [x] 1.2 Write failing tests: 缺失必需字段或 finding assertion 格式非法时 fixture validation failure
- [x] 1.3 Implement: fixture loader / validator
- [x] 1.4 Verify green: 运行 `uv run pytest tests/evaluation/test_reflection_report_eval.py -x -q`

## 2. Deterministic runner

- [x] 2.1 Write failing tests: runner patch observability public API 并调用 `run_reflection(scope)`
- [x] 2.2 Write failing tests: runner patch memory public API 并验证 expected findings
- [x] 2.3 Write failing tests: runner 验证 forbidden findings 不出现
- [x] 2.4 Write failing tests: runner 使用 tmp SQLite 并验证 persisted payload 不含 forbidden transcript snippets
- [x] 2.5 Implement: deterministic reflection report evaluation runner
- [x] 2.6 Verify green: 运行 `uv run pytest tests/evaluation/test_reflection_report_eval.py -x -q`

## 3. Baseline evaluation scenarios

- [x] 3.1 Write failing tests: repeated memory fact fixture 必须产生 `memory_candidate`
- [x] 3.2 Write failing tests: conflicting memory signals fixture 必须产生 `memory_conflict`
- [x] 3.3 Write failing tests: repeated task pattern fixture 必须产生 `skill_opportunity`
- [x] 3.4 Write failing tests: noisy negative fixture 不应产生 findings
- [x] 3.5 Write failing tests: transcript redaction fixture 不应持久化 raw user_input / agent_reply
- [x] 3.6 Implement: baseline fixtures and runner expectations
- [x] 3.7 Verify green: 运行 `uv run pytest tests/evaluation/test_reflection_report_eval.py -x -q`

## 4. Optional real-route smoke guard

- [x] 4.1 Write failing tests: 未设置 `FLEETENT_EVAL_REAL_REFLECTION=1` 时真实 route smoke 被 skip
- [x] 4.2 Write failing tests: 设置 opt-in 但缺少 explicit local fixture/config 时真实 route smoke 被 skip
- [x] 4.3 Implement: opt-in real-route smoke guard
- [x] 4.4 Verify green: 运行 `uv run pytest tests/evaluation/test_reflection_report_eval.py -x -q`

## 5. Docs and final verification

- [x] 5.1 更新 `docs/capabilities/reflection.md`
- [x] 5.2 更新 `docs/capabilities/intelligence-roadmap.md`
- [x] 5.3 更新 CI quality gate spec，说明 reflection report evaluation 不进入默认 PR gate
- [x] 5.4 运行 `uv run pytest tests/evaluation/test_reflection_report_eval.py -x -q`
- [x] 5.5 运行 `uv run ruff format src tests`
- [x] 5.6 运行 `uv run ruff check src tests`
- [x] 5.7 运行 `uv run mypy src`
- [x] 5.8 运行 `uv run pytest -x -q`
- [x] 5.9 运行 `openspec validate reflection-report-evaluation --strict`
- [x] 5.10 运行 `git diff --check`
