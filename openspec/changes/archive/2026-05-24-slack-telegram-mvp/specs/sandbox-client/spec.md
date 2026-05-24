## ADDED Requirements

### Requirement: Per-session workspace lifecycle
The system SHALL create a microsandbox workspace at session start and destroy it at session end.

#### Scenario: Workspace creation
- **WHEN** a session receives its first message
- **THEN** `sandbox_client.create_workspace(session_id)` is called and a MicroVM workspace is available

#### Scenario: Workspace destruction
- **WHEN** a session ends (no more messages in the current interaction)
- **THEN** `sandbox_client.destroy_workspace(session_id)` is called and the MicroVM is torn down

### Requirement: Tool execution in sandbox
The system SHALL route shell/code execution tool calls through the sandbox client.

#### Scenario: Shell command execution
- **WHEN** agent calls a sandboxed tool (e.g., `shell`) with a command
- **THEN** `sandbox_client.exec(session_id, command)` sends the command to the MicroVM and returns stdout/stderr

#### Scenario: File state persists within session
- **WHEN** agent writes a file in step 1 and reads it in step 2 of the same session
- **THEN** the file is present in step 2 (workspace state persists across tool calls within a session)

### Requirement: Cross-session isolation
Workspaces from different sessions SHALL be fully isolated.

#### Scenario: Session isolation
- **WHEN** session A writes `secret.txt` to its workspace
- **THEN** session B cannot read `secret.txt` (separate MicroVM)

### Requirement: Sandbox failure handling
The system SHALL handle microsandbox connectivity failures gracefully.

#### Scenario: microsandbox-server unreachable
- **WHEN** `sandbox_client.exec()` fails because microsandbox-server is down
- **THEN** the tool returns an error message to the agent; the agent decides whether to retry or inform the user

### Requirement: Host connectivity
The system SHALL connect to microsandbox-server via `host.docker.internal` when running inside Docker.

#### Scenario: Docker to host connection
- **WHEN** mini-agent runs in a Docker container
- **THEN** `sandbox_client` uses `http://host.docker.internal:<port>` as the microsandbox-server base URL
