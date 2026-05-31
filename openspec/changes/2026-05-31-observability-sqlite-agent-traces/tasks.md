## 0. 前置确认

- [ ] 0.1 确认本 change 不实现 structured logging、platform UI、metrics 聚合、source attribution
- [ ] 0.2 确认本 change 删除旧 JSONL trace API，不做 `log_run()` / `log()` / `fleetent.eval_logger` 兼容

## 1. Trace 数据模型与 public API

- [ ] 1.1 Write failing tests: `fleetent.observability` 导出 `TraceEvent`、`TraceQuery`、`record_trace_event`、`query_trace_events`
- [ ] 1.2 实现 trace 数据模型与 public API 入口，暂用未接库的最小骨架
- [ ] 1.3 运行 `uv run pytest -x -q`，确认 1.1 红测转绿

## 2. traces 表 migration

- [ ] 2.1 Write failing tests: Alembic upgrade 后存在 `traces` 表和必要索引
- [ ] 2.2 新增 Alembic migration 创建 `traces` 表与索引
- [ ] 2.3 运行 `uv run pytest -x -q`，确认 2.1 红测转绿

## 3. record_trace_event 写入

- [ ] 3.1 Write failing tests: `record_trace_event()` 写入 SQLite，并生成缺省 `id` / `ts`
- [ ] 3.2 通过 database runtime 实现 trace 写入
- [ ] 3.3 运行 `uv run pytest -x -q`，确认 3.1 红测转绿

## 4. query_trace_events 查询

- [ ] 4.1 Write failing tests: `query_trace_events()` 支持按 run/user/agent/tenant/event_type/time range/limit 查询
- [ ] 4.2 实现 TraceQuery 到 SQL 的转换，使用 named parameters
- [ ] 4.3 运行 `uv run pytest -x -q`，确认 4.1 红测转绿

## 5. payload 脱敏、截断与序列化 fallback

- [ ] 5.1 Write failing tests: token/password/email/phone 被脱敏，大字段被截断，不可 JSON 序列化字段有 fallback 标记
- [ ] 5.2 实现 trace payload 写入前处理
- [ ] 5.3 运行 `uv run pytest -x -q`，确认 5.1 红测转绿

## 6. 删除 legacy eval_logger API

- [ ] 6.1 Write failing tests: `fleetent.eval_logger` import 不再可用，`fleetent.observability` 不再导出 `log_run` / `log` / `TRACE_PATH`
- [ ] 6.2 删除 `src/fleetent/eval_logger.py` shim，移除旧 JSONL eval_logger API
- [ ] 6.3 删除或重写 legacy JSONL 测试
- [ ] 6.4 运行 `uv run pytest -x -q`，确认 6.1 红测转绿

## 7. agent-runtime 接入

- [ ] 7.1 Write failing tests: `agent_loop.run()` 完成后记录 `agent_run_completed` trace event
- [ ] 7.2 Write failing tests: `agent_loop.run_stream()` 完成后记录 `agent_run_completed` trace event，并包含 token usage
- [ ] 7.3 修改 agent-runtime 使用 `record_trace_event()`，不再调用 `log_run()`
- [ ] 7.4 运行 `uv run pytest -x -q`，确认 7.1 / 7.2 红测转绿

## 8. 不写 JSONL

- [ ] 8.1 Write failing tests: agent run 后不会创建或追加 `data/traces.jsonl`
- [ ] 8.2 移除所有 JSONL trace 写入路径
- [ ] 8.3 运行 `uv run pytest -x -q`，确认 8.1 红测转绿

## 9. 收尾验证

- [ ] 9.1 运行 `uv run pytest -x -q`
- [ ] 9.2 运行 `uv run ruff format src tests`
- [ ] 9.3 运行 `uv run ruff check src tests`
- [ ] 9.4 运行 `uv run mypy src`
- [ ] 9.5 运行 `openspec validate 2026-05-31-observability-sqlite-agent-traces`
