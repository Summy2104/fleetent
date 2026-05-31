## Why

structured logging 和 SQLite agent traces 已经建立了 observability 的数据入口。下一步需要一个稳定的
usage summary API，让 platform、quota、运营分析和管理员排障可以按 user / agent / tenant / 时间窗口
查看调用次数、token 用量和耗时。

当前 traces 已记录 `agent_run_completed` event，payload 中包含 token usage、elapsed seconds 和 model
信息。第一版 usage summary 可以直接从 traces 实时聚合，不需要新表或后台 rollup job。

## What Changes

- 扩展 `observability` capability，新增 usage summary 查询能力。
- 新增 public API：
  - `UsageQuery`
  - `UsageSummary`
  - `ModelUsage`
  - `get_usage_summary(query)`
- 基于 `query_trace_events()` 读取 `agent_run_completed` events。
- 支持按 user、agent、tenant、session、时间范围过滤。
- 聚合：
  - run_count
  - prompt_tokens
  - completion_tokens
  - total_tokens
  - total_elapsed_s
  - avg_elapsed_s
  - by_model
- 对缺失 token usage 或 elapsed 的历史 trace 采用 0 值处理，不抛错。

## Capabilities

### New Capabilities

- 无新增 capability；扩展既有 `observability` capability 的 usage summary 子域。

### Modified Capabilities

- `observability`：新增只读 usage summary 聚合 API。

## Impact

- **代码**：
  - 在 `fleetent.observability` 下新增 usage summary API。
  - 复用现有 `query_trace_events()`，不直接访问 `traces` 表。
- **数据**：
  - 不新增表。
  - 不新增 migration。
- **不包含**：
  - 不做 dashboard UI。
  - 不做 Prometheus / OpenTelemetry。
  - 不做 `usage_rollups` 表。
  - 不做 quota enforcement。
  - 不做美元成本换算。
  - 不做工具耗时 / LLM 分段耗时统计。
