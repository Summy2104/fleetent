## ADDED Requirements

### Requirement: Generate fires deliver only via the scheduler

A `generate` task's fired agent run SHALL NOT expose the outbound delivery tools
(`send_im_message`, `send_file`) in its tool schema. A `generate` task's semantics are
"produce the notification body; the scheduler delivers the final reply" — so the model
produces content only and MUST NOT perform its own delivery, which would duplicate the
scheduler's broadcast. The fire path SHALL request this suppression when invoking the agent
loop for a `generate` task (e.g. `run(..., suppress_outbound_tools=True)`).

An `action` task's fired run SHALL retain the outbound delivery tools, because an `action`
task's semantics are "the agent acts via its own tools" and the scheduler does not broadcast
its reply. The fire-time connector snapshot (so outbound tools reach live connectors) is
unaffected and continues to be injected for runs that use outbound tools.

This suppression covers the builtin outbound tools only; MCP write tools are out of scope
(deployment-specific, and typically disabled by the MCP server's own policy).

#### Scenario: Generate fire suppresses outbound tools

- **WHEN** a `generate` task fires and the scheduler invokes the agent loop
- **THEN** the run is invoked with outbound-tool suppression (`suppress_outbound_tools=True`)
  so `send_im_message`/`send_file` are absent from the run's tool schema, and delivery of the
  final reply is performed solely by the scheduler

#### Scenario: Action fire retains outbound tools

- **WHEN** an `action` task fires and the scheduler invokes the agent loop
- **THEN** the run is invoked without outbound-tool suppression, so the agent can deliver via
  its own outbound tools, and the scheduler does not broadcast the reply
