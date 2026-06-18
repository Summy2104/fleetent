## ADDED Requirements

### Requirement: Platform server does not import agent runtime execution

`server.py` SHALL NOT import `fleetent.runtime.run_stream` or any other agent-loop execution entry point. The admin console playground (`/admin/chat/*`) is the only path that required this import; with playground removed, the platform process has no reason to execute an agent loop in-process.

#### Scenario: Platform starts without runtime execution import

- **WHEN** the platform app starts
- **THEN** `server.py` does not import `run_stream` or any equivalent agent-loop callable from `fleetent.runtime`

#### Scenario: Admin console does not run agent turns in-process

- **WHEN** an admin uses the admin console
- **THEN** no agent loop turn is executed inside the platform process; agent execution remains exclusively in `fleetent agent run` processes
