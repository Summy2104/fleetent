# tasks

## 1. OpenSpec proposal

- [x] 创建 proposal、design、tasks 和 observability spec delta
- [x] 运行 `openspec validate 2026-06-02-observability-admin-query-api --strict` 确认 proposal 有效

## 2. Trace query CLI

- [x] Write failing tests：在 `tests/integration/test_admin.py` 添加 `fleetent-admin observability traces` 测试，覆盖 filter 参数、payload keys 输出和 payload secret value 不输出
- [x] Verify red：运行 `uv run pytest tests/integration/test_admin.py -x -q`，确认因命令不存在或输出不符合预期失败
- [x] Implement：在 `src/fleetent/admin.py` 添加 `observability traces` 子命令，解析 filter 并调用 `query_trace_events(TraceQuery(...))`
- [x] Verify green：运行 `uv run pytest tests/integration/test_admin.py -x -q`，确认 trace CLI 测试通过

## 3. Usage query CLI

- [x] Write failing tests：在 `tests/integration/test_admin.py` 添加 `fleetent-admin observability usage` 测试，覆盖 filter 参数和 summary / by-model 输出
- [x] Verify red：运行 `uv run pytest tests/integration/test_admin.py -x -q`，确认 usage CLI 测试失败
- [x] Implement：在 `src/fleetent/admin.py` 添加 `observability usage` 子命令，调用 `get_usage_summary(UsageQuery(...))`
- [x] Verify green：运行 `uv run pytest tests/integration/test_admin.py -x -q`，确认 usage CLI 测试通过

## 4. Performance query CLI

- [x] Write failing tests：在 `tests/integration/test_admin.py` 添加 `fleetent-admin observability performance` 测试，覆盖 filter 参数和 run / LLM / tool / permission 指标输出
- [x] Verify red：运行 `uv run pytest tests/integration/test_admin.py -x -q`，确认 performance CLI 测试失败
- [x] Implement：在 `src/fleetent/admin.py` 添加 `observability performance` 子命令，调用 `get_performance_summary(PerformanceQuery(...))`
- [x] Verify green：运行 `uv run pytest tests/integration/test_admin.py -x -q`，确认 performance CLI 测试通过

## 5. 文档与验证

- [x] 更新 `docs/capabilities/observability.md`、`docs/capabilities/deployment.md`、`docs/capabilities/intelligence-roadmap.md`
- [x] 运行相关分层测试：`uv run pytest tests/integration/test_admin.py -x -q`
- [x] 运行 `uv run ruff format src tests`
- [x] 运行 `uv run ruff check src tests`
- [x] 运行 `uv run mypy src`
- [x] 运行 `uv run pytest -x -q`
- [x] 运行 `openspec validate 2026-06-02-observability-admin-query-api --strict`
- [x] 运行 `git diff --check`
- [x] 所有 checkbox 完成后归档 change 并验证 `openspec/specs/observability/spec.md`
