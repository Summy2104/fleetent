## ADDED Requirements

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
