# observability Specification

## Purpose
定义 fleetent 的 observability 行为边界。当前规范覆盖 structured logging：程序日志、
启动诊断、脱敏基线、console/file 输出和日志通道故障隔离。agent run traces、usage metrics
和 dashboard 由后续 changes 独立扩展。

> 注：structured logger 的**模块归属/放置**契约（顶层基础设施模块 `fleetent.structured_logging`
> + 依赖方向规则 + 旧路径迁移）已移交 `structured-logging` spec 承载；本 spec 仅保留其
> **行为** requirements（public API / level / 通道 / 脱敏 / 故障隔离），不再定义其物理位置。
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

系统 SHALL 同时支持 console human-readable 输出和 file JSONL 输出。文件日志 SHALL 写入按日期命名的日志文件。Platform/server 默认文件日志目录 SHALL be `FLEETENT_HOME/logs/`; agent runtime SHALL explicitly configure its own file log directory as `<agent-home>/data/logs/`.

#### Scenario: Write platform JSONL file log
- **WHEN** platform/server structured logging 使用默认目录，且一条日志通过 file level 过滤
- **THEN** 系统向 `FLEETENT_HOME/logs/YYYY-MM-DD.log` 追加一行 JSON
- **AND** 不创建 `FLEETENT_HOME/data/logs/YYYY-MM-DD.log`

#### Scenario: Write platform error file log
- **WHEN** platform/server 默认目录下一条 `warn`、`error` 或 `fatal` 日志通过 file level 过滤
- **THEN** 系统同时向 `FLEETENT_HOME/logs/YYYY-MM-DD.error.log` 追加一行 JSON

#### Scenario: Write agent JSONL file log
- **WHEN** agent runtime 启动并应用 agent logging config
- **THEN** agent 程序日志默认写入 `<agent-home>/data/logs/YYYY-MM-DD.log`
- **AND** 不写入 `FLEETENT_HOME/logs/` 或 `FLEETENT_HOME/data/logs/`

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

系统 SHALL 将 structured program logs 与 agent run traces 分开存储和查询。Platform structured logs 默认在 `FLEETENT_HOME/logs/`；agent structured logs 默认在 `<agent-home>/data/logs/`；agent run traces 存储在 agent-side trace table，legacy JSONL fallback 若仍存在则必须在 `<agent-home>/data/traces.jsonl`。

#### Scenario: Program log does not write trace table
- **WHEN** 组件通过 structured logger 写入程序日志
- **THEN** 系统不会把该日志写入 `traces` 表，也不会把它作为 reflection 数据源

#### Scenario: Legacy JSONL trace is not home-level
- **WHEN** legacy trace logger is used inside an agent runtime process
- **THEN** it SHALL NOT write `FLEETENT_HOME/data/traces.jsonl`

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
`query_trace_events()` SHALL 支持按 run、user、agent、tenant、event_type、时间范围和 limit 查询 trace events。其中 agent 维度字段为 `agent_name`（agent 侧 trace 以 agent slug/name 记，列名为 `agent_name`，不再叫 `agent_id`——身份模型 R2：agent 侧不出现 agent id）。

#### Scenario: Query by run id
- **WHEN** 调用 `query_trace_events(TraceQuery(run_id="run-1"))`
- **THEN** 只返回 `run_id` 为 `run-1` 的事件

#### Scenario: Query by agent and time range
- **WHEN** 调用 `query_trace_events()` 并传入 `agent_name`、start_ts 和 end_ts
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
- **WHEN** 查询包含 agent_name、start_ts 和 end_ts
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

### Requirement: Observability contract test coverage
系统 SHALL 通过自动化 contract tests 验证 agent run 的核心 observability 事件链路。

#### Scenario: Contract tests live in integration layer
- **WHEN** 新增 observability contract tests
- **THEN** 测试文件位于 `tests/integration/`
- **AND** 不向平铺 `tests/` 根目录新增 contract test

#### Scenario: Non-streaming run trace contract is tested
- **WHEN** `agent_loop.run()` 完成且注入了 long-term context sources
- **THEN** 测试覆盖 `injected_context` 与 `agent_run_completed` 两类事件
- **AND** 测试断言两类事件共享同一个 run_id

#### Scenario: Streaming run trace contract is tested
- **WHEN** `agent_loop.run_stream()` 完成且注入了 long-term context sources
- **THEN** 测试覆盖 `injected_context` 与 `agent_run_completed` 两类事件
- **AND** 测试断言两类事件共享同一个 run_id

### Requirement: Observability payload safety tests
系统 SHALL 通过自动化测试验证 trace payload 的安全边界。

#### Scenario: Source attribution raw content is excluded
- **WHEN** source metadata 包含 `content`、`text` 或 `transcript`
- **THEN** 测试断言落库 payload 不包含这些完整原文

#### Scenario: Sensitive payload is redacted
- **WHEN** trace payload 包含 token、password、secret、邮箱或手机号
- **THEN** 测试断言落库 payload 中敏感值被脱敏

#### Scenario: Large payload is truncated
- **WHEN** trace payload 包含超过阈值的大字段
- **THEN** 测试断言落库 payload 被截断并带截断标记

### Requirement: Usage summary ignores non-completion events
系统 SHALL 通过自动化测试验证 usage summary 只统计 completed run events。

#### Scenario: Injected context does not affect usage
- **WHEN** 同一个 run 同时存在 `injected_context` 和 `agent_run_completed`
- **THEN** 测试断言 usage summary 只按 `agent_run_completed` 统计 run_count 和 token totals

### Requirement: Agent runtime lifecycle trace events
agent-runtime SHALL record lifecycle events for each run using the existing trace API.

#### Scenario: Non-streaming run start is recorded
- **WHEN** `agent_loop.run()` starts processing a user message
- **THEN** it records `event_type="agent_run_started"`
- **AND** the event includes run_id、user_id、agent_name when available、entrypoint=`run`

#### Scenario: Streaming run start is recorded
- **WHEN** `agent_loop.run_stream()` starts processing a user message
- **THEN** it records `event_type="agent_run_started"`
- **AND** the event includes run_id、user_id、agent_name when available、entrypoint=`run_stream`

#### Scenario: Run failure is recorded
- **WHEN** an agent run fails before emitting a completed event
- **THEN** it records `event_type="agent_run_failed"`
- **AND** the event includes error_type、error_message、elapsed_s and entrypoint

### Requirement: LLM call trace events
agent-runtime SHALL record each LLM call attempt and outcome.

#### Scenario: LLM call start is recorded
- **WHEN** agent-runtime sends a request to a model provider
- **THEN** it records `event_type="llm_call_started"`
- **AND** the event includes model、task_type、streaming flag、message_count and tool_schema_count

#### Scenario: LLM call completion is recorded
- **WHEN** the model provider returns successfully
- **THEN** it records `event_type="llm_call_completed"`
- **AND** the event includes model、finish_reason when available、elapsed_s and token usage when available

#### Scenario: LLM call failure is recorded
- **WHEN** a model provider call raises an error
- **THEN** it records `event_type="llm_call_failed"`
- **AND** the event includes model、error_type、error_message and elapsed_s

### Requirement: Model fallback trace events
agent-runtime SHALL record each fallback model switch.

#### Scenario: Fallback switch is recorded
- **WHEN** the primary model call fails with a fallback-eligible error and agent-runtime tries a fallback model
- **THEN** it records `event_type="model_fallback_triggered"`
- **AND** the event includes from_model、to_model、reason and attempt_index

#### Scenario: Exhausted fallback remains visible
- **WHEN** all fallback attempts fail
- **THEN** the trace contains the failed LLM call events for each attempted model
- **AND** the run records `agent_run_failed`

### Requirement: Tool call trace events
agent-runtime SHALL record tool call start, completion, and failure events.

#### Scenario: Tool call start is recorded
- **WHEN** the model requests a tool call
- **THEN** agent-runtime records `event_type="tool_call_started"`
- **AND** the event includes tool_name、tool_call_id、risk_level and sanitized argument summary

#### Scenario: Tool call completion is recorded
- **WHEN** a tool call returns successfully
- **THEN** agent-runtime records `event_type="tool_call_completed"`
- **AND** the event includes tool_name、tool_call_id、elapsed_s and sanitized result summary

#### Scenario: Tool call failure is recorded
- **WHEN** dispatching or awaiting a tool call fails
- **THEN** agent-runtime records `event_type="tool_call_failed"`
- **AND** the event includes tool_name、tool_call_id、error_type、error_message and elapsed_s

#### Scenario: Sub-agent tool call is covered
- **WHEN** agent-runtime intercepts the `sub_agent` tool
- **THEN** it records the same tool call started/completed/failed event types as ordinary tools

### Requirement: Permission trace events
agent-runtime SHALL record human approval request and resolution events for medium/high risk tools.

#### Scenario: Permission request is recorded
- **WHEN** a medium or high risk tool requires approval
- **THEN** agent-runtime records `event_type="permission_requested"`
- **AND** the event includes approval_id、tool_name、risk_level and requester_user_id

#### Scenario: Permission resolution is recorded
- **WHEN** the approval request resolves as approved、rejected or timeout
- **THEN** agent-runtime records `event_type="permission_resolved"`
- **AND** the event includes approval_id、tool_name、risk_level、decision and elapsed_s

### Requirement: Context compression trace events
agent-runtime SHALL record context compression outcomes when runtime message compression is triggered.

#### Scenario: Compression is recorded
- **WHEN** runtime context compression changes the message list before an LLM call
- **THEN** agent-runtime records `event_type="context_compression_completed"`
- **AND** the event includes reason、before_message_count、after_message_count and elapsed_s

#### Scenario: No-op compression is not recorded
- **WHEN** context compression is checked but does not change the message list
- **THEN** agent-runtime does not record a context compression event

### Requirement: Final reply trace event
agent-runtime SHALL record when a final reply is emitted to the caller.

#### Scenario: Non-streaming final reply is recorded
- **WHEN** `agent_loop.run()` returns a final reply
- **THEN** it records `event_type="final_reply_emitted"`
- **AND** the event includes reply_length and elapsed_s

#### Scenario: Streaming final reply is recorded
- **WHEN** `agent_loop.run_stream()` emits the final `done` event
- **THEN** it records `event_type="final_reply_emitted"`
- **AND** the event includes reply_length and elapsed_s

### Requirement: Runtime event payload safety
Runtime trace events SHALL store bounded summaries, not raw full runtime content.

#### Scenario: Prompt and transcript are not persisted
- **WHEN** runtime events are recorded
- **THEN** payloads do not include raw full prompt, full message transcript, or full final reply

#### Scenario: Tool args and results are bounded
- **WHEN** tool call events include arguments or results
- **THEN** the payload contains sanitized summaries with truncation markers when needed

### Requirement: Runtime events are correlated by run id
All trace events emitted by a single agent runtime invocation SHALL share the same run_id.

#### Scenario: Non-streaming runtime events share run id
- **WHEN** `agent_loop.run()` records lifecycle, LLM, tool, permission, injected_context, final_reply, and completed events
- **THEN** all events from that invocation share one run_id

#### Scenario: Streaming runtime events share run id
- **WHEN** `agent_loop.run_stream()` records lifecycle, LLM, tool, injected_context, final_reply, and completed events
- **THEN** all events from that invocation share one run_id

### Requirement: Performance summary public API
系统 SHALL 提供 performance summary public API，用于从 runtime trace events 聚合性能和失败指标。

#### Scenario: Performance API is importable
- **WHEN** 调用方从 `fleetent.observability` 导入 `PerformanceQuery`、`PerformanceSummary` 和 `get_performance_summary`
- **THEN** 导入成功

#### Scenario: Empty performance summary
- **WHEN** 查询范围内没有 trace events
- **THEN** summary 的计数、耗时、错误率和分组列表均为 0 或空列表

### Requirement: Performance summary reads through trace API
performance summary SHALL 通过 `query_trace_events()` 读取 traces，而不是直接访问 SQLite `traces` 表。

#### Scenario: Performance summary uses trace query API
- **WHEN** `get_performance_summary()` 执行查询
- **THEN** 它调用 `query_trace_events()`，并传入 TraceQuery 支持的 query filters
- **AND** 它不直接访问 SQLite `traces` 表

### Requirement: Performance query filters
系统 SHALL 支持按 user、agent、tenant、session、时间范围和 limit 过滤 performance summary。

#### Scenario: Filter by user
- **WHEN** 调用 `get_performance_summary(PerformanceQuery(user_id="user-1"))`
- **THEN** summary 只统计 user-1 的 trace events

#### Scenario: Filter by session
- **WHEN** 查询包含 session_id
- **THEN** summary 在读取 trace API 后按 `TraceEvent.session_id` 过滤
- **AND** summary 只统计该 session 的 trace events

#### Scenario: Filter by agent and time range
- **WHEN** 查询包含 agent_name、start_ts 和 end_ts
- **THEN** summary 只统计该 agent 在时间范围内的 trace events

### Requirement: Run-level performance metrics
系统 SHALL 从 terminal agent run lifecycle events 聚合 run-level performance metrics。

#### Scenario: Run counts and failure rate
- **WHEN** traces 中包含 `agent_run_completed` 和 `agent_run_failed`
- **THEN** summary 返回 run_count、completed_count、failed_count 和 failure_rate
- **AND** run_count 等于 completed_count + failed_count

#### Scenario: Run latency percentiles
- **WHEN** completed 或 failed run events 包含合法 elapsed_s
- **THEN** summary 返回 avg_elapsed_s、p50_elapsed_s 和 p95_elapsed_s

### Requirement: LLM and fallback metrics
系统 SHALL 从 LLM runtime events 聚合 LLM 调用、错误、耗时和 fallback 指标。

#### Scenario: LLM call metrics
- **WHEN** traces 中包含 `llm_call_completed` 和 `llm_call_failed`
- **THEN** summary 返回 llm_call_count、llm_error_count、avg_llm_elapsed_s 和 p95_llm_elapsed_s

#### Scenario: Fallback metrics
- **WHEN** traces 中包含 `model_fallback_triggered`
- **THEN** summary 返回 fallback_count 和 fallback_rate

#### Scenario: Group by model
- **WHEN** LLM events 包含多个 model
- **THEN** summary.by_model 按 model 返回 call_count、error_count 和 avg_elapsed_s

### Requirement: Tool performance metrics
系统 SHALL 从 tool runtime events 聚合工具调用、错误和耗时指标。

#### Scenario: Tool call metrics
- **WHEN** traces 中包含 `tool_call_completed` 和 `tool_call_failed`
- **THEN** summary 返回 tool_call_count、tool_error_count、avg_tool_elapsed_s 和 p95_tool_elapsed_s

#### Scenario: Group by tool
- **WHEN** tool events 包含多个 tool_name
- **THEN** summary.by_tool 按 tool_name 返回 call_count、error_count 和 avg_elapsed_s
- **AND** by_tool 按 call_count 降序、tool_name 升序稳定排序

### Requirement: Permission wait metrics
系统 SHALL 从 permission runtime events 聚合人工审批数量和等待耗时。

#### Scenario: Permission decisions are counted
- **WHEN** traces 中包含 `permission_requested` 和 `permission_resolved` events
- **THEN** summary 返回 permission_requested_count、permission_approved_count、permission_rejected_count 和 permission_timeout_count

#### Scenario: Permission wait time is averaged
- **WHEN** permission resolved events 包含合法 elapsed_s
- **THEN** summary 返回 avg_permission_wait_s

### Requirement: Performance payload tolerance
系统 SHALL 容忍旧 trace、不完整 trace 或非法 payload 字段。

#### Scenario: Missing elapsed is excluded from latency samples
- **WHEN** runtime event payload 缺失 elapsed_s
- **THEN** event count aggregation still counts the event
- **AND** latency aggregation excludes that event from average and percentile samples
- **AND** summary does not raise

#### Scenario: Invalid numeric fields are excluded from latency samples
- **WHEN** runtime event payload 中的 elapsed_s 不是合法数字
- **THEN** event count aggregation still counts the event
- **AND** latency aggregation excludes that event from average and percentile samples
- **AND** summary does not raise

#### Scenario: Missing grouping keys use unknown
- **WHEN** LLM event 缺失 model 或 tool event 缺失 tool_name
- **THEN** 对应分组归入 `unknown`

### Requirement: Knowledge-base scope diagnostics
系统 SHALL 对 agent KB 范围解析失败或降级记录可诊断事件，帮助 Pilot 环境排查配置问题。

#### Scenario: Default KB missing is diagnostic
- **WHEN** agent 没有显式 KB 绑定
- **AND** 默认 KB 未配置、为空或不可用
- **THEN** 系统记录一条知识库范围诊断事件
- **AND** 事件包含 `tenant_id`、`agent_name` 和原因

#### Scenario: Scope diagnostics avoid sensitive content
- **WHEN** 系统记录知识库范围诊断事件
- **THEN** 事件不包含完整用户 query、文档正文、connector credential、token 或 secret

### Requirement: Diagnostics export
系统 SHALL 提供手动 diagnostics export，用于生成本地脱敏诊断包。

#### Scenario: Export creates package with manifest
- **WHEN** operator 运行 diagnostics export
- **THEN** 系统创建本地诊断包
- **AND** 包含 `manifest.json`

#### Scenario: Export includes diagnostic data
- **WHEN** operator 运行 diagnostics export
- **THEN** 诊断包可包含指定时间范围内的 structured logs、trace events 或 trace 摘要、usage summary、
  performance summary、connector status、environment summary 和 config summary

#### Scenario: Export excludes business data
- **WHEN** operator 运行 diagnostics export
- **THEN** 诊断包不包含 memory 内容、KB 文档正文、KB chunks、SQLite 主库、SQLite backups 或 connector credential 文件内容

#### Scenario: Export excludes full user content
- **WHEN** trace 或 log 中包含用户消息、prompt、reply 或工具 payload
- **THEN** 诊断包不包含完整原文
- **AND** 大文本被截断并带有截断标记

#### Scenario: Export performs second-pass redaction
- **WHEN** 诊断包写入 logs、traces、config summary 或 error summary
- **THEN** 系统再次脱敏 token、API key、password、secret、authorization、邮箱和手机号

### Requirement: Diagnostics retention planning
系统 SHALL 支持诊断数据 retention dry-run，用于展示将删除的候选但不修改数据。

#### Scenario: Dry-run identifies old logs
- **WHEN** 配置了 `diagnostics.retention.logs_days`
- **THEN** retention dry-run 返回超过天数的 log 文件候选

#### Scenario: Dry-run identifies old traces
- **WHEN** 配置了 `diagnostics.retention.traces_days`
- **THEN** retention dry-run 返回超过天数的 trace 记录数量

#### Scenario: Dry-run identifies old diagnostic exports
- **WHEN** 配置了 `diagnostics.retention.diagnostic_exports_days`
- **THEN** retention dry-run 返回超过天数的 diagnostics export 包候选

#### Scenario: Dry-run does not mutate
- **WHEN** operator 运行 retention dry-run
- **THEN** 系统不删除文件
- **AND** 不删除 trace 记录

### Requirement: Diagnostics retention apply
系统 SHALL 支持显式手动 retention apply，且只清理诊断数据。

#### Scenario: Apply disabled by default
- **WHEN** `diagnostics.retention.enabled=false`
- **AND** operator 运行 retention apply
- **THEN** 系统 fail fast
- **AND** 不删除任何文件或 trace 记录

#### Scenario: Apply deletes only configured old logs
- **WHEN** `diagnostics.retention.enabled=true`
- **AND** 配置了 `logs_days`
- **THEN** retention apply 只删除超过天数的 log 文件

#### Scenario: Apply deletes only configured old traces
- **WHEN** `diagnostics.retention.enabled=true`
- **AND** 配置了 `traces_days`
- **THEN** retention apply 只删除超过天数的 observability trace 记录

#### Scenario: Apply deletes only configured old exports
- **WHEN** `diagnostics.retention.enabled=true`
- **AND** 配置了 `diagnostic_exports_days`
- **THEN** retention apply 只删除超过天数的 diagnostics export 包

#### Scenario: Apply never deletes business data
- **WHEN** operator 运行 retention apply
- **THEN** 系统不删除 memory、KB documents、KB chunks、vector index、users、agents、schedules、connector source state、
  SQLite 主库或 SQLite backups

#### Scenario: Apply tolerates per-file deletion failure
- **WHEN** 删除某个诊断文件失败
- **THEN** 系统记录该失败
- **AND** 继续处理其他候选

### Requirement: Diagnostics admin CLI
系统 SHALL 在 `fleetent admin` 中提供 diagnostics export 和 retention 手动操作命令。

#### Scenario: Export from CLI
- **WHEN** operator 运行 `fleetent admin diagnostics export`
- **THEN** CLI 调用 diagnostics export 并输出诊断包路径

#### Scenario: Retention dry-run from CLI
- **WHEN** operator 运行 `fleetent admin diagnostics retention dry-run`
- **THEN** CLI 输出将删除的诊断数据候选摘要
- **AND** 不删除任何数据

#### Scenario: Retention apply from CLI
- **WHEN** operator 运行 `fleetent admin diagnostics retention apply`
- **THEN** CLI 执行手动 retention apply 或在 retention disabled 时返回非 0

#### Scenario: Diagnostics CLI output is sanitized
- **WHEN** CLI 输出 export、dry-run 或 apply 结果
- **THEN** 输出不包含 token、secret、credential payload 或完整文档正文

### Requirement: session 模块结构化日志覆盖

`session/manager.py` SHALL 使用 `get_logger("session.manager")` 记录所有 session 操作事件，包括清理、容量淘汰和维护触发。MUST NOT 使用 `structlog` 或 `stdlib logging`，以确保日志落盘和自动脱敏。

#### Scenario: session 清理日志落盘
- **WHEN** `cleanup_expired()` 删除过期 session 文件或 `enforce_capacity()` 淘汰 session
- **THEN** 相关事件通过 `get_logger("session.manager")` 记录，写入 `data/logs/YYYY-MM-DD.log` JSONL 文件

#### Scenario: session 维护失败日志脱敏
- **WHEN** session 维护操作记录包含 session_id 或错误信息的 warn 日志
- **THEN** 日志内容经过自动脱敏处理（Bearer token、API key、邮箱等被替换）
