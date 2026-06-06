## ADDED Requirements

### Requirement: session 模块结构化日志覆盖

`session/manager.py` SHALL 使用 `get_logger("session.manager")` 记录所有 session 操作事件，包括清理、容量淘汰和维护触发。MUST NOT 使用 `structlog` 或 `stdlib logging`，以确保日志落盘和自动脱敏。

#### Scenario: session 清理日志落盘
- **WHEN** `cleanup_expired()` 删除过期 session 文件或 `enforce_capacity()` 淘汰 session
- **THEN** 相关事件通过 `get_logger("session.manager")` 记录，写入 `data/logs/YYYY-MM-DD.log` JSONL 文件

#### Scenario: session 维护失败日志脱敏
- **WHEN** session 维护操作记录包含 session_id 或错误信息的 warn 日志
- **THEN** 日志内容经过自动脱敏处理（Bearer token、API key、邮箱等被替换）
