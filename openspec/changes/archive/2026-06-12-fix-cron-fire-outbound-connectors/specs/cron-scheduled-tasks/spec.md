## MODIFIED Requirements

### Requirement: Cron trigger fires agent run asynchronously
When a scheduled task's trigger (cron/once/interval) matches the current time, the scheduler SHALL call `agent_loop.run()` with the task's `message`, `user_id`, (if configured) resolved agent system prompt and allowed tools, **and the `outbound_connectors` snapshot resolved from the connector registry at fire time** so that outbound tools invoked inside the fired run (e.g. `send_im_message`) can reach the agent's live IM connectors. The trigger SHALL NOT block the scheduler event loop, and the run result SHALL be recorded in the observability trace.

#### Scenario: Agent run triggered on schedule

- **WHEN** a task's trigger fires
- **THEN** `agent_loop.run()` is invoked with the task's message and user_id without blocking the scheduler loop

#### Scenario: Fired run can deliver via IM tools

- **WHEN** a task fires whose message asks the agent to send a message/notification to a channel or user
- **THEN** the agent run receives the fire-time `outbound_connectors` snapshot, and an outbound IM tool invoked inside the run reaches the live connector (the run is not told "no connector available")

#### Scenario: No connectors available degrades cleanly

- **WHEN** a task fires while no IM connector is registered for the agent
- **THEN** `agent_loop.run()` receives an empty `outbound_connectors` mapping and the run proceeds without error

#### Scenario: Run outcome recorded in runtime-state columns

- **WHEN** a triggered agent run completes or fails
- **THEN** the task's `last_run_at`, `last_status`, and (on failure) `last_error` are updated and the run is written to the eval trace
