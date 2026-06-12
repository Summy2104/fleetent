## MODIFIED Requirements

### Requirement: Graceful drain on SIGUSR1

The agent process SHALL handle SIGUSR1 as a graceful drain signal with the following
ordered shutdown chain: stop accepting new work (IM supervisors and the cron scheduler
stop first), wait for all in-flight `loop.run()` calls to complete (up to the drain
timeout), **then release all MCP session hosts via `aclose_all()`**, then exit cleanly.
The drain timeout SHALL be configurable via `FLEETENT_RESTART_DRAIN_TIMEOUT` (seconds,
default 30). Every step of the shutdown chain SHALL be **contained**: wrapped with its
own exception handling and a bounded timeout, so a failing or hanging component is
logged and skipped while the remaining steps still run. A teardown error in any
component MUST NOT propagate to other components and MUST NOT change the process exit
code: the graceful drain path SHALL exit with code 0.

#### Scenario: Drain completes before timeout

- **WHEN** SIGUSR1 is received and all in-flight requests complete within drain_timeout
- **THEN** the process stops the IM supervisors and scheduler, waits for the active run
  count to reach zero, releases MCP session hosts, and exits with code 0

#### Scenario: Drain timeout exceeded

- **WHEN** SIGUSR1 is received and active runs do not complete within drain_timeout
- **THEN** the process logs the remaining run count, still releases MCP session hosts,
  and exits anyway (allowing SIGTERM from the restart command)
- **AND** in-flight requests are interrupted

#### Scenario: Teardown error is contained

- **WHEN** any shutdown step (IM supervisor stop, scheduler shutdown, MCP host close)
  raises or hangs past its step timeout
- **THEN** the failure is logged as a warning, the remaining shutdown steps still
  execute, and the process still exits with code 0

#### Scenario: Graceful restart leaves no crash trace

- **WHEN** `fleetent agent restart` triggers SIGUSR1 on a healthy agent
- **THEN** the old process exits with code 0 and no traceback is written to the journal
