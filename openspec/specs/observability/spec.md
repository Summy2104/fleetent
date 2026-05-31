# observability Specification

## Purpose
定义 fleetent 的 observability 行为边界。当前规范覆盖 structured logging：程序日志、
启动诊断、脱敏基线、console/file 输出和日志通道故障隔离。agent run traces、usage metrics
和 dashboard 由后续 changes 独立扩展。
## Requirements
### Requirement: Structured logger public API
系统 SHALL 提供 observability structured logger public API，供组件按 component 名称写入结构化程序日志。

#### Scenario: Get component logger
- **WHEN** 组件调用 `get_logger("server")`
- **THEN** 系统返回一个 logger，后续日志事件包含 component=`server`

#### Scenario: Logger supports standard levels
- **WHEN** 调用 logger 的 `fatal`、`error`、`warn`、`info`、`debug` 或 `trace` 方法
- **THEN** 系统按对应 level 处理日志事件

### Requirement: Logging level filtering
系统 SHALL 支持 `silent` / `fatal` / `error` / `warn` / `info` / `debug` / `trace` 七级日志，并允许 console
与 file 通道分别配置 level。

#### Scenario: Console and file levels differ
- **WHEN** console level 为 `info` 且 file level 为 `debug`
- **THEN** debug 日志不会输出到 console，但会写入 file

#### Scenario: Silent channel
- **WHEN** 某个输出通道 level 为 `silent`
- **THEN** 该通道不输出任何日志

### Requirement: Console and file outputs
系统 SHALL 同时支持 console human-readable 输出和 file JSONL 输出。文件日志 SHALL 写入按日期命名的日志文件。

#### Scenario: Write JSONL file log
- **WHEN** 一条日志通过 file level 过滤
- **THEN** 系统向 `data/logs/YYYY-MM-DD.log` 追加一行 JSON

#### Scenario: Write error file log
- **WHEN** 一条 `warn`、`error` 或 `fatal` 日志通过 file level 过滤
- **THEN** 系统同时向 `data/logs/YYYY-MM-DD.error.log` 追加一行 JSON

#### Scenario: Non-error log does not enter error file
- **WHEN** 一条 `info`、`debug` 或 `trace` 日志通过 file level 过滤
- **THEN** 系统不会把该日志写入 error file

### Requirement: Log event shape
系统 SHALL 为文件日志写入稳定 JSON 结构，至少包含 timestamp、level、component、message 和 fields。

#### Scenario: Structured fields are persisted
- **WHEN** 调用 logger 写入 message 和结构化字段
- **THEN** 文件日志 JSON 包含 `ts`、`level`、`component`、`message` 和 `fields`

#### Scenario: Exception details are persisted
- **WHEN** 调用 logger 写入异常信息
- **THEN** 文件日志 JSON 包含异常类型、异常消息、stack、文件名和行号

### Requirement: Redaction baseline
系统 SHALL 在日志输出到 console 或 file 前执行脱敏基线，避免常见 secret 和个人联系方式明文落盘。

#### Scenario: Token values are redacted
- **WHEN** 日志 message 或 fields 中包含 Bearer token、API key、password、secret、token、api_key 或 authorization
- **THEN** 输出内容中的敏感值被不可逆脱敏

#### Scenario: Contact values are redacted
- **WHEN** 日志 message 或 fields 中包含邮箱地址或中国大陆手机号
- **THEN** 输出内容中的对应值被不可逆脱敏

### Requirement: Startup diagnostics
系统 SHALL 在启动路径记录关键诊断日志，帮助部署方定位启动失败或降级原因。

#### Scenario: Database path is not writable
- **WHEN** database runtime 初始化发现数据库路径不可写
- **THEN** 系统写入包含组件名、失败原因和建议动作的 `fatal` 或 `error` 日志

#### Scenario: Optional dependency degrades
- **WHEN** MCP server 配置存在但不可达，且系统可以继续启动
- **THEN** 系统写入包含组件名、失败原因和建议动作的 `warn` 日志

### Requirement: Output failure isolation
系统 SHALL 隔离日志输出通道失败，避免日志系统故障影响业务请求。

#### Scenario: File output fails
- **WHEN** file 日志写入失败
- **THEN** logger 调用不会向业务调用方抛出异常，console 通道仍可继续输出

#### Scenario: Console output fails
- **WHEN** console 日志写入失败
- **THEN** logger 调用不会向业务调用方抛出异常，file 通道仍可继续输出

### Requirement: Structured logs are not agent traces
系统 SHALL 将 structured program logs 与 agent run traces 分开存储和查询。

#### Scenario: Program log does not write trace table
- **WHEN** 组件通过 structured logger 写入程序日志
- **THEN** 系统不会把该日志写入 `traces` 表，也不会把它作为 reflection 数据源

### Requirement: Trace event public API
系统 SHALL 提供明确的 agent run trace public API：`record_trace_event(event)`、
`query_trace_events(query)`、`TraceEvent` 和 `TraceQuery`。

#### Scenario: Record trace event API exists
- **WHEN** 调用方从 `fleetent.observability` 导入 `record_trace_event` 和 `TraceEvent`
- **THEN** 导入成功，且可构造一条 trace event

#### Scenario: Query trace events API exists
- **WHEN** 调用方从 `fleetent.observability` 导入 `query_trace_events` 和 `TraceQuery`
- **THEN** 导入成功，且可构造查询条件

### Requirement: No legacy trace logging API
系统 SHALL 删除旧的 JSONL trace API，不保留向后兼容 wrapper。

#### Scenario: Legacy eval_logger import removed
- **WHEN** 调用方导入 `fleetent.eval_logger`
- **THEN** 导入失败或明确不可用

#### Scenario: Legacy trace functions are not public
- **WHEN** 调用方从 `fleetent.observability` 导入 `log_run`、`log` 或 `TRACE_PATH`
- **THEN** 导入失败或对应名称不存在

### Requirement: Trace table storage
系统 SHALL 将 agent run trace events 存储在 observability-owned SQLite `traces` 表中。

#### Scenario: Migration creates trace table
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 `traces` 表

#### Scenario: Migration creates trace indexes
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含按 run、user/time、agent/time、tenant/event/time 查询所需索引

### Requirement: Record trace event
`record_trace_event()` SHALL 写入一条 trace event，并在缺省情况下生成 event id 与 timestamp。

#### Scenario: Record event with generated id and timestamp
- **WHEN** 调用 `record_trace_event()` 写入未携带 id 和 ts 的 `TraceEvent`
- **THEN** `traces` 表中出现一条带 id 和 ts 的记录

#### Scenario: Payload is persisted as JSON
- **WHEN** trace event 带有 payload
- **THEN** payload 被序列化到 `payload_json`

### Requirement: Query trace events
`query_trace_events()` SHALL 支持按 run、user、agent、tenant、event_type、时间范围和 limit 查询 trace events。

#### Scenario: Query by run id
- **WHEN** 调用 `query_trace_events(TraceQuery(run_id="run-1"))`
- **THEN** 只返回 `run_id` 为 `run-1` 的事件

#### Scenario: Query by agent and time range
- **WHEN** 调用 `query_trace_events()` 并传入 agent_id、start_ts 和 end_ts
- **THEN** 只返回该 agent 在时间范围内的事件

#### Scenario: Query limit
- **WHEN** 查询条件包含 `limit=10`
- **THEN** 最多返回 10 条事件

### Requirement: Trace payload safety
系统 SHALL 在 trace payload 落库前执行脱敏、截断和 JSON 序列化 fallback。

#### Scenario: Sensitive payload values are redacted
- **WHEN** payload 中包含 token、password、secret、邮箱或手机号
- **THEN** 落库内容中的敏感值被不可逆脱敏

#### Scenario: Large payload values are truncated
- **WHEN** payload 中包含超过阈值的大字段
- **THEN** 落库内容被截断，并包含截断标记

#### Scenario: Non-serializable payload has fallback
- **WHEN** payload 中包含不可 JSON 序列化对象
- **THEN** 系统将该值转换为字符串，并标记 `serialization_fallback=true`

### Requirement: Agent runtime records completed run
agent-runtime SHALL 在 run 完成后记录 `agent_run_completed` trace event。

#### Scenario: Non-streaming run records trace
- **WHEN** `agent_loop.run()` 成功完成
- **THEN** 系统写入一条 `event_type=agent_run_completed` 的 trace event

#### Scenario: Streaming run records trace with usage
- **WHEN** `agent_loop.run_stream()` 成功完成并获得 token usage
- **THEN** 系统写入一条包含 token usage 的 `agent_run_completed` trace event

### Requirement: No JSONL trace output
系统 SHALL 不再创建或追加 `data/traces.jsonl`。

#### Scenario: Agent run does not write JSONL
- **WHEN** 任意 agent run 完成
- **THEN** 系统不会创建或追加 `data/traces.jsonl`

### Requirement: Trace and structured logging naming separation
系统 SHALL 将 `log` 命名留给 structured logging，不用于 agent run trace public API。

#### Scenario: Trace API does not expose log names
- **WHEN** 调用方查看 `fleetent.observability` public API
- **THEN** agent trace 相关能力通过 `record_trace_event` 和 `query_trace_events` 暴露，而不是 `log` 或 `log_run`

### Requirement: Usage summary public API
系统 SHALL 提供 usage summary public API，用于从 agent run traces 聚合调用次数、token 用量和耗时。

#### Scenario: Usage API is importable
- **WHEN** 调用方从 `fleetent.observability` 导入 `UsageQuery`、`UsageSummary`、`ModelUsage` 和 `get_usage_summary`
- **THEN** 导入成功

### Requirement: Usage summary source events
usage summary SHALL 只统计 `agent_run_completed` trace events。

#### Scenario: Ignore other event types
- **WHEN** traces 中同时存在 `agent_run_completed` 和其他 event_type
- **THEN** usage summary 只统计 `agent_run_completed`

### Requirement: Basic usage aggregation
系统 SHALL 聚合 run_count、prompt_tokens、completion_tokens、total_tokens、total_elapsed_s 和 avg_elapsed_s。

#### Scenario: Empty usage summary
- **WHEN** 查询范围内没有 completed run
- **THEN** summary 的 run_count、tokens、elapsed 和 average 均为 0

#### Scenario: Aggregate multiple runs
- **WHEN** 查询范围内有多条 completed run trace
- **THEN** summary 返回这些 run 的数量、token 总和、elapsed 总和和平均 elapsed

### Requirement: Usage query filters
系统 SHALL 支持按 user、agent、tenant、session 和时间范围过滤 usage summary。

#### Scenario: Filter by user
- **WHEN** 调用 `get_usage_summary(UsageQuery(user_id="user-1"))`
- **THEN** summary 只包含 user-1 的 completed runs

#### Scenario: Filter by agent and time range
- **WHEN** 查询包含 agent_id、start_ts 和 end_ts
- **THEN** summary 只包含该 agent 在时间范围内的 completed runs

#### Scenario: Filter by session
- **WHEN** 查询包含 session_id
- **THEN** summary 只包含该 session 的 completed runs

### Requirement: Usage by model
系统 SHALL 按 model 聚合 usage，并返回稳定排序的 `by_model` 列表。

#### Scenario: Group usage by model
- **WHEN** completed runs 使用多个 model
- **THEN** summary.by_model 按 model 分别返回 run_count、tokens 和 elapsed

#### Scenario: Sort model usage
- **WHEN** 返回多个 model usage
- **THEN** by_model 按 total_tokens 降序排列；total_tokens 相同时按 model 升序排列

### Requirement: Usage payload tolerance
系统 SHALL 容忍旧 trace 或不完整 trace 中缺失或非法的 usage payload 字段。

#### Scenario: Missing token usage counts as zero
- **WHEN** completed run payload 缺失 tokens 字段
- **THEN** token 聚合按 0 处理，不抛出异常

#### Scenario: Missing elapsed counts as zero
- **WHEN** completed run payload 缺失 elapsed_s
- **THEN** elapsed 聚合按 0 处理，不抛出异常

#### Scenario: Missing model groups as unknown
- **WHEN** completed run payload 缺失 model_used
- **THEN** 该 run 归入 model=`unknown`

### Requirement: Usage summary reads through trace API
usage summary SHALL 通过 `query_trace_events()` 读取 traces，而不是直接访问 SQLite `traces` 表。

#### Scenario: Usage summary uses trace query API
- **WHEN** `get_usage_summary()` 执行查询
- **THEN** 它调用 `query_trace_events()`，并传入 event_type=`agent_run_completed`

### Requirement: Injected context trace public API
系统 SHALL 提供 `InjectedContextTrace` 和 `record_injected_context(run_id, sources, ...)`
public API，用于记录最终注入 prompt 的长期上下文来源摘要。

#### Scenario: Public API is importable
- **WHEN** 调用方从 `fleetent.observability` 导入 `InjectedContextTrace` 和 `record_injected_context`
- **THEN** 导入成功

#### Scenario: Injected context source shape
- **WHEN** 调用方构造 `InjectedContextTrace`
- **THEN** 该对象包含 source_id、source_type、score、token_estimate 和 metadata

#### Scenario: Unknown token estimate is explicit
- **WHEN** 单个 source 的 token estimate 暂不可得
- **THEN** 调用方可以设置 `token_estimate=0`
- **AND** payload 中仍包含 token_estimate 字段

### Requirement: Injected context trace event
`record_injected_context()` SHALL 将来源摘要写为 `event_type="injected_context"` 的 trace event。

#### Scenario: Record injected context event
- **WHEN** 调用 `record_injected_context(run_id="run-1", sources=[source])`
- **THEN** `traces` 表中出现 run_id=`run-1` 且 event_type=`injected_context` 的事件

#### Scenario: Sources are persisted as summary
- **WHEN** injected_context event 被写入
- **THEN** payload 包含 sources summary
- **AND** 每个 source summary 包含 source_id、source_type、score、token_estimate 和 metadata

### Requirement: Source attribution content safety
系统 SHALL 默认只保存来源摘要，不保存完整 memory、knowledge content 或完整对话 transcript。

#### Scenario: Raw content is not persisted
- **WHEN** `record_injected_context()` 写入 sources
- **THEN** payload 中不包含 `content`、`text` 或 `transcript` 字段

#### Scenario: Sensitive metadata is redacted
- **WHEN** source metadata 中包含 token、password、secret、邮箱或手机号
- **THEN** 落库 payload 中的敏感值被现有 trace payload safety 规则脱敏

### Requirement: Empty injected context is skipped
系统 SHALL 在没有实际注入来源时跳过 injected_context trace event。

#### Scenario: Empty sources are not recorded
- **WHEN** 调用 `record_injected_context(run_id="run-1", sources=[])`
- **THEN** 系统不写入 injected_context trace event

### Requirement: Agent runtime records injected context sources
agent-runtime SHALL 在 long-term-ctx 注入长期上下文后记录实际注入的来源摘要。

#### Scenario: Run id is shared across injected context and completion
- **WHEN** 一次 agent run 同时写入 injected_context 和 agent_run_completed trace events
- **THEN** 两类事件使用同一个 run_id

#### Scenario: Non-streaming run records sources
- **WHEN** `agent_loop.run()` 从 long-term-ctx 得到非空 `BuiltContext.sources`
- **THEN** 系统调用 `record_injected_context()` 记录这些 sources

#### Scenario: Streaming run records sources
- **WHEN** `agent_loop.run_stream()` 从 long-term-ctx 得到非空 `BuiltContext.sources`
- **THEN** 系统调用 `record_injected_context()` 记录这些 sources

#### Scenario: Agent runtime skips empty sources
- **WHEN** long-term-ctx 返回空 sources
- **THEN** agent-runtime 不写 injected_context trace event

### Requirement: Injected context events are queryable
injected_context events SHALL 通过现有 trace query API 查询，不引入单独查询表。

#### Scenario: Query injected context events
- **WHEN** 调用 `query_trace_events(TraceQuery(event_type="injected_context"))`
- **THEN** 返回匹配的来源归因 trace events

