## 0. 前置确认

- [x] 0.1 确认本 change 只实现 structured logging，不迁移 `log_run()` / `log()`
- [x] 0.2 确认本 change 不创建 `traces` 表，不实现 platform UI，不引入外部 APM

## 1. 配置与默认值

- [x] 1.1 Write failing tests: 未配置时 logging 默认 console=`info`、file=`debug`、directory=`data/logs`
- [x] 1.2 实现 `observability.logging` 配置加载与默认值
- [x] 1.3 运行 `uv run pytest -x -q`，确认 1.1 红测转绿

## 2. Logger public API

- [x] 2.1 Write failing tests: `get_logger(component)` 返回支持七级方法的 logger，并保留 component 字段
- [x] 2.2 在 `fleetent.observability` 下实现 structured logger public API
- [x] 2.3 运行 `uv run pytest -x -q`，确认 2.1 红测转绿

## 3. Level 过滤与双通道输出

- [x] 3.1 Write failing tests: console/file 分别按 level 过滤，`silent` 关闭对应通道
- [x] 3.2 实现 console human-readable 输出与 file JSONL 输出
- [x] 3.3 运行 `uv run pytest -x -q`，确认 3.1 红测转绿

## 4. 文件落盘与 error 分流

- [x] 4.1 Write failing tests: 自动创建 `data/logs/`，全量文件写所有通过 file level 的日志，error 文件只写 warn/error/fatal
- [x] 4.2 实现按日期文件落盘与 error 文件分流
- [x] 4.3 运行 `uv run pytest -x -q`，确认 4.1 红测转绿

## 5. 脱敏基线

- [x] 5.1 Write failing tests: Bearer token、API key、password/secret/token 字段、邮箱、手机号写入前被脱敏
- [x] 5.2 实现日志 message 与 fields 的统一 redaction
- [x] 5.3 运行 `uv run pytest -x -q`，确认 5.1 红测转绿

## 6. 异常与写入失败处理

- [x] 6.1 Write failing tests: exception 日志包含 error_type/error_message/stack/file/line
- [x] 6.2 Write failing tests: console 写入失败不影响 file；file 写入失败不影响 console，也不抛到业务调用方
- [x] 6.3 实现异常字段提取、JSON 序列化 fallback、单通道失败隔离
- [x] 6.4 运行 `uv run pytest -x -q`，确认 6.1 / 6.2 红测转绿

## 7. 启动诊断接入

- [x] 7.1 Write failing tests: database 路径不可写时启动诊断日志包含组件、失败原因和建议动作
- [x] 7.2 接入 config / database runtime / provider key / MCP server 的启动诊断日志
- [x] 7.3 运行 `uv run pytest -x -q`，确认 7.1 红测转绿

## 8. 收尾验证

- [x] 8.1 运行 `uv run pytest -x -q`
- [x] 8.2 运行 `uv run ruff format src tests`
- [x] 8.3 运行 `uv run ruff check src tests`
- [x] 8.4 运行 `uv run mypy src`
- [x] 8.5 运行 `openspec validate 2026-05-31-observability-structured-logging`
