## ADDED Requirements

### Requirement: Restart running agent via `fleetent agent restart`

The `fleetent` command SHALL provide `agent restart <agent-id> [--port N] [--home PATH]`
that stops the currently running agent process gracefully and boots a fresh one in its place.
The command SHALL send SIGUSR1 to trigger graceful drain, wait up to `drain_timeout` seconds
(default 30s) for in-flight requests to complete, then fall back to SIGTERM (5s) and finally
SIGKILL if the process does not exit.

#### Scenario: Restart a running agent

- **WHEN** `fleetent agent restart support` is invoked and `<home>/.fleetent.pid` contains
  a live PID
- **THEN** SIGUSR1 is sent to the running process
- **AND** the running process stops accepting new IM messages and waits for in-flight requests
- **AND** after the old process exits, a new agent process boots and runs in the foreground

#### Scenario: Restart with no running process is idempotent

- **WHEN** `fleetent agent restart support` is invoked and no `.fleetent.pid` exists (or
  the recorded process is already gone)
- **THEN** the command silently skips the kill step and boots the agent normally

#### Scenario: SIGTERM fallback after drain timeout

- **WHEN** in-flight requests do not complete within `drain_timeout` seconds after SIGUSR1
- **THEN** SIGTERM is sent to force-terminate the process
- **AND** if the process does not exit within 5 more seconds, SIGKILL is sent

### Requirement: `serve()` maintains a PID file

`serve()` SHALL write the current process ID to `<home_dir>/.fleetent.pid` before
booting the agent, and SHALL delete the file on exit (clean or crash).

#### Scenario: PID file exists while agent is running

- **WHEN** `fleetent agent run support` is executing
- **THEN** `<home>/.fleetent.pid` exists and contains the integer process ID

#### Scenario: PID file removed on shutdown

- **WHEN** the `fleetent agent run` process exits (normally or via signal)
- **THEN** `<home>/.fleetent.pid` no longer exists

### Requirement: Graceful drain on SIGUSR1

The agent process SHALL handle SIGUSR1 as a graceful drain signal: stop accepting new
IM messages, wait for all in-flight `loop.run()` calls to complete, then exit cleanly.
The drain timeout SHALL be configurable via `FLEETENT_RESTART_DRAIN_TIMEOUT` (seconds,
default 30).

#### Scenario: Drain completes before timeout

- **WHEN** SIGUSR1 is received and all in-flight requests complete within drain_timeout
- **THEN** the process stops the IM supervisor, waits for active run count to reach zero,
  then exits normally

#### Scenario: Drain timeout exceeded

- **WHEN** SIGUSR1 is received and active runs do not complete within drain_timeout
- **THEN** the process exits anyway (allowing SIGTERM from the restart command)
- **AND** in-flight requests are interrupted

### Requirement: Active run counter in `loop.run()`

`loop.run()` SHALL maintain a module-level integer counter `_active_runs` that is
incremented on entry and decremented in a `finally` block on exit.

#### Scenario: Counter reflects in-flight runs

- **WHEN** N concurrent calls to `loop.run()` are executing
- **THEN** `loop._active_runs == N`

#### Scenario: Counter decrements on error

- **WHEN** `loop.run()` raises an exception
- **THEN** `_active_runs` is still decremented (via finally)
