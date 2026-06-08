# agent-log-format-wiring Specification

## Purpose
定义 standalone agent runtime（`fleetent agent run`）如何从 `agent.yaml` 的 `log_format`
和 `observability.logging.*` 字段配置结构化日志系统。确保日志格式（JSON / console）和
级别（console_level / file_level）可按 agent 独立配置，且平台服务（`server.py`）继续
从 `Settings`（环境变量）读取，互不干扰。

## Requirements

### Requirement: Standalone agent runtime configures logging from agent.yaml

A standalone `fleetent agent run` process SHALL configure the structured logging system
from the active agent's `log_format` and `observability.logging` fields immediately after
loading the agent home. `log_format: "json"` SHALL produce JSON-formatted log output;
`log_format: "console"` (default) SHALL produce human-readable console output. The
`observability.logging.console_level`, `file_level`, and `directory` fields SHALL be
forwarded to `configure_structured_logging`. This configuration SHALL be applied before
any agent loop runs.

#### Scenario: console log format applied at boot

- **WHEN** an agent's `agent.yaml` declares `log_format: console`
- **THEN** `boot()` calls `configure_structured_logging` with the console renderer and the
  agent's logging level and directory settings

#### Scenario: JSON log format applied at boot

- **WHEN** an agent's `agent.yaml` declares `log_format: json`
- **THEN** `boot()` calls `configure_structured_logging` with the JSON renderer and the
  agent's logging level and directory settings

#### Scenario: platform server is unaffected

- **WHEN** the platform server (uvicorn / `server.py`) starts
- **THEN** it continues to read `log_format` from `Settings`, not from any agent file
