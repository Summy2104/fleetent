# agent-log-format-wiring

## ADDED Requirements

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
