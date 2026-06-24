## MODIFIED Requirements

### Requirement: Cron trigger fires agent run asynchronously
When a scheduled task's trigger (cron/once/interval) matches the current time, the scheduler SHALL fire **according to the task's `task_type`**: `notify` sends `notify_text` verbatim via the fire-time connector snapshot **without invoking `agent_loop.run`**; `generate` and `action` call `agent_loop.run()` with the task's `message`, `user_id`, resolved agent context, and the fire-time `outbound_connectors` snapshot. For `generate`, the run additionally receives the scheduled-run delivery statement AND is invoked with outbound-tool suppression (`suppress_outbound_tools=True`) so the run produces only the notification body and the scheduler performs the sole delivery (`send_im_message`/`send_file` are absent from a generate run's tool schema). For `action`, the run retains the outbound tools (so the agent delivers via its own tools and the scheduler does not broadcast). The trigger SHALL NOT block the scheduler event loop, and the run result SHALL be recorded in the observability trace. `last_status` SHALL reflect the **task intent** outcome per type — notify: delivery outcome; generate: run + delivery outcome; action: run outcome — never merely "the delivery API call succeeded".

#### Scenario: Notify fire bypasses the agent
- **WHEN** a `notify` task's trigger fires
- **THEN** the scheduler sends `notify_text` to the resolved target without calling `agent_loop.run`

#### Scenario: Agent run triggered on schedule
- **WHEN** a `generate` or `action` task's trigger fires
- **THEN** `agent_loop.run()` is invoked with the task's message and user_id without blocking the scheduler loop

#### Scenario: Action fire can deliver via IM tools
- **WHEN** an `action` task fires whose message asks the agent to send a message/notification to a channel or user
- **THEN** the agent run receives the fire-time `outbound_connectors` snapshot AND retains the outbound tools, so an outbound IM tool invoked inside the run reaches the live connector (the run is not told "no connector available")

#### Scenario: Generate fire produces content but does not self-deliver
- **WHEN** a `generate` task fires
- **THEN** `agent_loop.run()` is invoked with `suppress_outbound_tools=True` so `send_im_message`/`send_file` are absent from the run's schema, and the final reply is delivered solely by the scheduler's broadcast

#### Scenario: No connectors available degrades cleanly
- **WHEN** a task fires while no IM connector is registered for the agent
- **THEN** `agent_loop.run()` receives an empty `outbound_connectors` mapping and the run proceeds without error

#### Scenario: Run outcome recorded in runtime-state columns
- **WHEN** a triggered agent run completes or fails
- **THEN** the task's `last_run_at`, `last_status`, and (on failure) `last_error` are updated and the run is written to the eval trace
