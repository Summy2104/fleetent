## Overview

本 change 将 observability 的第一步限定为程序日志。目标是让开发和私有化部署时的排障信息稳定、
可过滤、可落盘、可脱敏；agent run 业务事件仍由后续 `observability-sqlite-agent-traces`
change 单独处理。

## Boundaries

Structured logging 负责进程级与组件级事件，例如：

- 服务启动 / 关闭
- 配置加载结果与错误
- database runtime 初始化失败或降级
- MCP server 不可达
- tool / sandbox / connector 的可恢复错误
- 组件级 debug 信息

Structured logging 不负责：

- 一次 agent run 的完整事件流
- reflection 查询的数据源
- token 用量聚合
- platform dashboard UI
- 外部日志采集器部署

## Public API

`fleetent.observability` 提供：

```python
def get_logger(component: str) -> Logger:
    """Return a structured logger for a component."""
```

Logger 至少支持：

- `fatal(message, **fields)`
- `error(message, **fields)`
- `warn(message, **fields)`
- `info(message, **fields)`
- `debug(message, **fields)`
- `trace(message, **fields)`

日志调用方传入结构化字段；logger 负责 level 过滤、脱敏、格式化和多通道写入。

## Configuration

新增 `observability.logging` 配置命名空间：

```yaml
observability:
  logging:
    console_level: info
    file_level: debug
    directory: data/logs
    json_file: true
```

默认行为：

- console level = `info`
- file level = `debug`
- directory = `data/logs`
- 文件格式 = JSONL
- error file 包含 `warn` / `error` / `fatal`

`silent` 关闭对应通道输出。

## Log Event Shape

文件日志每行是一条 JSON：

```json
{
  "ts": "2026-05-31T12:34:56.789Z",
  "level": "info",
  "component": "server",
  "message": "server started",
  "fields": {
    "host": "0.0.0.0",
    "port": 8000
  }
}
```

异常日志包含：

- `error_type`
- `error_message`
- `stack`
- `file`
- `line`

## Redaction

日志写入前对 message 和 fields 统一脱敏。第一版规则覆盖：

- Bearer token：`Authorization: Bearer ...`
- API key 样式值，例如 `sk-...`、`ma-<64hex>`
- 字段名包含 `password`、`secret`、`token`、`api_key`、`authorization`
- 邮箱地址
- 中国大陆手机号

脱敏不可逆，输出固定占位符，例如 `[REDACTED:token]`。

## Startup Diagnostics

启动路径应记录关键诊断事件：

- config 加载成功 / 失败
- database runtime 初始化成功 / 失败
- database 路径不可写
- 必要 provider API key 缺失
- MCP server 配置存在但不可达

诊断日志应包含组件名、失败原因和建议动作。启动失败时写 `fatal`；可降级时写 `warn`。

## Error Handling

- console 写入失败不得影响 file 写入。
- file 写入失败不得影响 console 写入，也不得导致 agent run 失败。
- 日志目录不存在时自动创建。
- JSON 序列化失败时，将不可序列化字段转成字符串并写 `serialization_fallback=true`。

## Testing

本 change 使用 TDD 执行。重点测试：

- level 过滤
- console / file 双通道输出
- error file 分流
- 日志目录自动创建
- 脱敏规则
- 异常字段与 stack 记录
- 单通道失败不影响另一通道
- 启动诊断日志可断言

## Future Work

后续独立 changes：

- `observability-sqlite-agent-traces`
- `observability-source-attribution`
- `observability-usage-metrics`
- `platform-observability-dashboard`
