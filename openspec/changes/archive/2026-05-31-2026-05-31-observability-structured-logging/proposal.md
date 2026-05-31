## Why

fleetent 当前缺少统一的程序日志体系。排查启动失败、配置错误、数据库不可写、外部连接降级、
工具执行异常时，开发者和部署方只能依赖零散 `print`、异常堆栈或 agent trace。agent trace
适合分析一次 agent run 的业务事件，但不适合承载进程级日志、启动诊断和组件级排障信息。

本 change 先建立 structured logging 基线，为后续 SQLite agent traces、usage metrics 和
platform dashboard 提供稳定的日志、脱敏和诊断基础。

## What Changes

- 新增 `observability` 能力中的 structured logging 需求。
- 提供 `get_logger(component)` 作为程序日志入口。
- 支持七级日志：`silent` / `fatal` / `error` / `warn` / `info` / `debug` / `trace`。
- 支持 console 与 file 双通道输出，并允许分别配置日志级别。
- 文件日志写入 `data/logs/YYYY-MM-DD.log`，warn/error/fatal 额外写入
  `data/logs/YYYY-MM-DD.error.log`。
- 文件日志使用 JSONL，console 输出使用 human-readable 格式。
- 日志写入前执行脱敏基线，覆盖 API key、Bearer token、password/secret/token 字段、邮箱和手机号。
- 增加启动诊断日志，覆盖配置解析、database 可写性、必要 API key、MCP server 可达性等关键启动检查。
- 明确 structured logs 不进入 `traces` 表，不作为 reflection 数据源。

## Capabilities

### New Capabilities

- `observability`：新增 structured logging、redaction baseline、startup diagnostics 行为。

### Modified Capabilities

- 无。SQLite agent traces、source attribution、metrics / usage 不在本 change 中实现。

## Impact

- **代码**：
  - 新增或扩展 `fleetent.observability` 下的 logging 模块。
  - 新增 `get_logger(component)` public API。
  - 在配置中增加 observability logging 相关配置。
  - 在启动路径接入关键诊断日志。
- **数据 / 文件**：
  - 新增本地日志目录 `data/logs/`。
  - 写入按日期滚动的 JSONL 日志文件。
- **安全**：
  - 日志落盘与 console 输出前统一脱敏。
  - 本 change 不实现完整 DLP，不承诺识别所有敏感业务内容。
- **不包含**：
  - 不迁移 `log_run()` / `log()`。
  - 不创建 SQLite `traces` 表。
  - 不实现 platform trace UI。
  - 不引入 OpenTelemetry、Prometheus 或外部 APM。
