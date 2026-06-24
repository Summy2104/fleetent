## MODIFIED Requirements

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

### Requirement: Structured logs are not agent traces

系统 SHALL 将 structured program logs 与 agent run traces 分开存储和查询。Platform structured logs 默认在 `FLEETENT_HOME/logs/`；agent structured logs 默认在 `<agent-home>/data/logs/`；agent run traces 存储在 agent-side trace table，legacy JSONL fallback 若仍存在则必须在 `<agent-home>/data/traces.jsonl`。

#### Scenario: Program log does not write trace table
- **WHEN** 组件通过 structured logger 写入程序日志
- **THEN** 系统不会把该日志写入 `traces` 表，也不会把它作为 reflection 数据源

#### Scenario: Legacy JSONL trace is not home-level
- **WHEN** legacy trace logger is used inside an agent runtime process
- **THEN** it SHALL NOT write `FLEETENT_HOME/data/traces.jsonl`
