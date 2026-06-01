## ADDED Requirements

### Requirement: Agent runtime lifecycle trace events
agent-runtime SHALL record lifecycle events for each run using the existing trace API.

#### Scenario: Non-streaming run start is recorded
- **WHEN** `agent_loop.run()` starts processing a user message
- **THEN** it records `event_type="agent_run_started"`
- **AND** the event includes run_id、user_id、agent_name when available、entrypoint=`run`

#### Scenario: Streaming run start is recorded
- **WHEN** `agent_loop.run_stream()` starts processing a user message
- **THEN** it records `event_type="agent_run_started"`
- **AND** the event includes run_id、user_id、agent_name when available、entrypoint=`run_stream`

#### Scenario: Run failure is recorded
- **WHEN** an agent run fails before emitting a completed event
- **THEN** it records `event_type="agent_run_failed"`
- **AND** the event includes error_type、error_message、elapsed_s and entrypoint

### Requirement: LLM call trace events
agent-runtime SHALL record each LLM call attempt and outcome.

#### Scenario: LLM call start is recorded
- **WHEN** agent-runtime sends a request to a model provider
- **THEN** it records `event_type="llm_call_started"`
- **AND** the event includes model、task_type、streaming flag、message_count and tool_schema_count

#### Scenario: LLM call completion is recorded
- **WHEN** the model provider returns successfully
- **THEN** it records `event_type="llm_call_completed"`
- **AND** the event includes model、finish_reason when available、elapsed_s and token usage when available

#### Scenario: LLM call failure is recorded
- **WHEN** a model provider call raises an error
- **THEN** it records `event_type="llm_call_failed"`
- **AND** the event includes model、error_type、error_message and elapsed_s

### Requirement: Model fallback trace events
agent-runtime SHALL record each fallback model switch.

#### Scenario: Fallback switch is recorded
- **WHEN** the primary model call fails with a fallback-eligible error and agent-runtime tries a fallback model
- **THEN** it records `event_type="model_fallback_triggered"`
- **AND** the event includes from_model、to_model、reason and attempt_index

#### Scenario: Exhausted fallback remains visible
- **WHEN** all fallback attempts fail
- **THEN** the trace contains the failed LLM call events for each attempted model
- **AND** the run records `agent_run_failed`

### Requirement: Tool call trace events
agent-runtime SHALL record tool call start, completion, and failure events.

#### Scenario: Tool call start is recorded
- **WHEN** the model requests a tool call
- **THEN** agent-runtime records `event_type="tool_call_started"`
- **AND** the event includes tool_name、tool_call_id、risk_level and sanitized argument summary

#### Scenario: Tool call completion is recorded
- **WHEN** a tool call returns successfully
- **THEN** agent-runtime records `event_type="tool_call_completed"`
- **AND** the event includes tool_name、tool_call_id、elapsed_s and sanitized result summary

#### Scenario: Tool call failure is recorded
- **WHEN** dispatching or awaiting a tool call fails
- **THEN** agent-runtime records `event_type="tool_call_failed"`
- **AND** the event includes tool_name、tool_call_id、error_type、error_message and elapsed_s

#### Scenario: Sub-agent tool call is covered
- **WHEN** agent-runtime intercepts the `sub_agent` tool
- **THEN** it records the same tool call started/completed/failed event types as ordinary tools

### Requirement: Permission trace events
agent-runtime SHALL record human approval request and resolution events for medium/high risk tools.

#### Scenario: Permission request is recorded
- **WHEN** a medium or high risk tool requires approval
- **THEN** agent-runtime records `event_type="permission_requested"`
- **AND** the event includes approval_id、tool_name、risk_level and requester_user_id

#### Scenario: Permission resolution is recorded
- **WHEN** the approval request resolves as approved、rejected or timeout
- **THEN** agent-runtime records `event_type="permission_resolved"`
- **AND** the event includes approval_id、tool_name、risk_level、decision and elapsed_s

### Requirement: Context compression trace events
agent-runtime SHALL record context compression outcomes when runtime message compression is triggered.

#### Scenario: Compression is recorded
- **WHEN** runtime context compression changes the message list before an LLM call
- **THEN** agent-runtime records `event_type="context_compression_completed"`
- **AND** the event includes reason、before_message_count、after_message_count and elapsed_s

#### Scenario: No-op compression is not recorded
- **WHEN** context compression is checked but does not change the message list
- **THEN** agent-runtime does not record a context compression event

### Requirement: Final reply trace event
agent-runtime SHALL record when a final reply is emitted to the caller.

#### Scenario: Non-streaming final reply is recorded
- **WHEN** `agent_loop.run()` returns a final reply
- **THEN** it records `event_type="final_reply_emitted"`
- **AND** the event includes reply_length and elapsed_s

#### Scenario: Streaming final reply is recorded
- **WHEN** `agent_loop.run_stream()` emits the final `done` event
- **THEN** it records `event_type="final_reply_emitted"`
- **AND** the event includes reply_length and elapsed_s

### Requirement: Runtime event payload safety
Runtime trace events SHALL store bounded summaries, not raw full runtime content.

#### Scenario: Prompt and transcript are not persisted
- **WHEN** runtime events are recorded
- **THEN** payloads do not include raw full prompt, full message transcript, or full final reply

#### Scenario: Tool args and results are bounded
- **WHEN** tool call events include arguments or results
- **THEN** the payload contains sanitized summaries with truncation markers when needed

### Requirement: Runtime events are correlated by run id
All trace events emitted by a single agent runtime invocation SHALL share the same run_id.

#### Scenario: Non-streaming runtime events share run id
- **WHEN** `agent_loop.run()` records lifecycle, LLM, tool, permission, injected_context, final_reply, and completed events
- **THEN** all events from that invocation share one run_id

#### Scenario: Streaming runtime events share run id
- **WHEN** `agent_loop.run_stream()` records lifecycle, LLM, tool, injected_context, final_reply, and completed events
- **THEN** all events from that invocation share one run_id
