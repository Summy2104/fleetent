## MODIFIED Requirements

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
