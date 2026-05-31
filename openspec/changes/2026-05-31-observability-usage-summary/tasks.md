## 0. 前置确认

- [ ] 0.1 确认本 change 只做 usage summary 查询 API，不做 UI、rollup 表、quota enforcement 或成本换算
- [ ] 0.2 确认本 change 基于已归档的 SQLite agent traces，只读取 `agent_run_completed`

## 1. Public API

- [ ] 1.1 Write failing tests: 可从 `fleetent.observability` 导入 `UsageQuery`、`UsageSummary`、`ModelUsage`、`get_usage_summary`
- [ ] 1.2 实现 usage summary dataclass 和 public API 入口
- [ ] 1.3 运行 `uv run pytest -x -q`，确认 1.1 红测转绿

## 2. 空结果和基础聚合

- [ ] 2.1 Write failing tests: 无 trace 时返回全 0 summary；多条 completed run 聚合 run_count、tokens、elapsed
- [ ] 2.2 实现基于 `query_trace_events()` 的基础聚合
- [ ] 2.3 运行 `uv run pytest -x -q`，确认 2.1 红测转绿

## 3. 过滤条件

- [ ] 3.1 Write failing tests: 支持按 user_id、agent_id、tenant_id、session_id、start_ts、end_ts 过滤
- [ ] 3.2 实现 UsageQuery 到 TraceQuery 的映射；session_id 如 TraceQuery 不支持则内存过滤
- [ ] 3.3 运行 `uv run pytest -x -q`，确认 3.1 红测转绿

## 4. by_model 聚合

- [ ] 4.1 Write failing tests: by_model 按 model 聚合 run_count、tokens、elapsed，并按 total_tokens 降序、model 升序排序
- [ ] 4.2 实现 ModelUsage 聚合和稳定排序
- [ ] 4.3 运行 `uv run pytest -x -q`，确认 4.1 红测转绿

## 5. 缺失和非法 payload 处理

- [ ] 5.1 Write failing tests: 缺失 tokens / elapsed_s / model_used 或非数字 token 不抛错，按 0 或 unknown 处理
- [ ] 5.2 实现 payload 容错解析
- [ ] 5.3 运行 `uv run pytest -x -q`，确认 5.1 红测转绿

## 6. 事件类型边界

- [ ] 6.1 Write failing tests: 非 `agent_run_completed` event 不参与 usage summary
- [ ] 6.2 确保查询固定 event_type 为 `agent_run_completed`
- [ ] 6.3 运行 `uv run pytest -x -q`，确认 6.1 红测转绿

## 7. 收尾验证

- [ ] 7.1 运行 `uv run pytest -x -q`
- [ ] 7.2 运行 `uv run ruff format src tests`
- [ ] 7.3 运行 `uv run ruff check src tests`
- [ ] 7.4 运行 `uv run mypy src`
- [ ] 7.5 运行 `openspec validate 2026-05-31-observability-usage-summary`
