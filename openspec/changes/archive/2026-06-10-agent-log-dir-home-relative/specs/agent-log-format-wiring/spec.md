# agent-log-format-wiring Delta

## MODIFIED Requirements

### Requirement: Standalone agent runtime configures logging from agent.yaml

A standalone `fleetent agent run` process SHALL configure the structured logging system
from the active agent's `log_format` and `observability.logging` fields immediately after
loading the agent home. `log_format: "json"` SHALL produce JSON-formatted log output;
`log_format: "console"` (default) SHALL produce human-readable console output. The
`observability.logging.console_level`, `file_level`, and `directory` fields SHALL be
forwarded to `configure_structured_logging`. The `directory` field SHALL be resolved
against the agent home before forwarding: a relative path resolves to
`<home_dir>/<directory>`; an absolute path is forwarded unchanged; an empty value
defaults to `<home_dir>/data/logs`. This configuration SHALL be applied before
any agent loop runs.

#### Scenario: console log format applied at boot

- **WHEN** an agent's `agent.yaml` declares `log_format: console`
- **THEN** `boot()` calls `configure_structured_logging` with the console renderer and the
  agent's logging level and directory settings

#### Scenario: JSON log format applied at boot

- **WHEN** an agent's `agent.yaml` declares `log_format: json`
- **THEN** `boot()` calls `configure_structured_logging` with the JSON renderer and the
  agent's logging level and directory settings

#### Scenario: relative directory resolves against agent home

- **WHEN** an agent's `agent.yaml` declares `observability.logging.directory: data/logs`
  (any non-absolute path)
- **THEN** `configure_structured_logging` receives `<home_dir>/data/logs`, regardless of
  the process working directory at launch

#### Scenario: absolute directory is forwarded unchanged

- **WHEN** an agent's `agent.yaml` declares an absolute `observability.logging.directory`
  (e.g. `/var/log/fleetent`)
- **THEN** `configure_structured_logging` receives that absolute path unchanged

#### Scenario: empty directory defaults to home data/logs

- **WHEN** an agent's `agent.yaml` leaves `observability.logging.directory` empty
- **THEN** `configure_structured_logging` receives `<home_dir>/data/logs`

#### Scenario: platform server is unaffected

- **WHEN** the platform server (uvicorn / `server.py`) starts
- **THEN** it continues to read `log_format` from `Settings`, not from any agent file
