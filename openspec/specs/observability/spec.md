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

