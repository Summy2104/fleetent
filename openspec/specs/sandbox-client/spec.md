# sandbox-client Specification

## Purpose
Defines sandbox workspace lifecycle, execution routing, isolation, failure handling, and host
connectivity expectations.
## Requirements

### Requirement: Tool execution in sandbox
The system SHALL route shell/code execution tool calls through the canonical sandbox execution surface, which is backed by the configured pluggable backend (Docker or microsandbox).

#### Scenario: Shell command execution
- **WHEN** agent calls a sandboxed tool with a command
- **THEN** the command is executed inside the selected backend's isolated workspace via the backend abstraction's `exec`, returning stdout/stderr/exit_code

#### Scenario: File state persists within session
- **WHEN** agent writes a file in step 1 and reads it in step 2 of the same session
- **THEN** the file is present in step 2

### Requirement: Cross-session isolation
Workspaces from different sessions SHALL be fully isolated, regardless of the selected backend.

#### Scenario: Session isolation
- **WHEN** session A writes `secret.txt` to its workspace
- **THEN** session B cannot read `secret.txt` (separate container on the Docker backend; separate microVM on the microsandbox backend)

### Requirement: Sandbox failure handling
The system SHALL handle backend connectivity failures gracefully.

#### Scenario: Selected backend unreachable
- **WHEN** a sandboxed tool execution fails because the selected backend is unavailable (Docker daemon down, or msb server unreachable)
- **THEN** the tool returns an error message to the agent; the agent decides whether to retry or inform the user
