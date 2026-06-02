# sandbox-client Specification

## Purpose
Defines sandbox workspace lifecycle, execution routing, isolation, failure handling, and host
connectivity expectations.
## Requirements
### Requirement: Per-session workspace lifecycle
The system SHALL create a sandbox workspace at session start and destroy it at session end through
`fleetent.integrations.sandbox`.

#### Scenario: Workspace creation
- **WHEN** a session receives its first message
- **THEN** `fleetent.integrations.sandbox.SandboxClient.create_workspace(session_id)` is called and a
  sandbox workspace is available

#### Scenario: Workspace destruction
- **WHEN** a session ends
- **THEN** `fleetent.integrations.sandbox.SandboxClient.destroy_workspace(session_id)` is called and the
  sandbox workspace is torn down

### Requirement: Tool execution in sandbox
The system SHALL route shell/code execution tool calls through the canonical sandbox client.

#### Scenario: Shell command execution
- **WHEN** agent calls a sandboxed tool with a command
- **THEN** `fleetent.integrations.sandbox.SandboxClient.exec(session_id, command)` sends the command to the
  sandbox backend and returns stdout/stderr

#### Scenario: File state persists within session
- **WHEN** agent writes a file in step 1 and reads it in step 2 of the same session
- **THEN** the file is present in step 2

### Requirement: Cross-session isolation
Workspaces from different sessions SHALL be fully isolated.

#### Scenario: Session isolation
- **WHEN** session A writes `secret.txt` to its workspace
- **THEN** session B cannot read `secret.txt` (separate MicroVM)

### Requirement: Sandbox failure handling
The system SHALL handle microsandbox connectivity failures gracefully.

#### Scenario: microsandbox-server unreachable
- **WHEN** `fleetent.integrations.sandbox.SandboxClient.exec()` fails because microsandbox-server is down
- **THEN** the tool returns an error message to the agent; the agent decides whether to retry or inform the user

### Requirement: Host connectivity
The system SHALL connect to microsandbox-server via `host.docker.internal` when running inside Docker.

#### Scenario: Docker to host connection
- **WHEN** fleetent runs in a Docker container
- **THEN** `fleetent.integrations.sandbox` uses `http://host.docker.internal:<port>` as the microsandbox-server base URL
