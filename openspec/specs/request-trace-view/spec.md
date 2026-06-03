# request-trace-view Specification

## Purpose
TBD - created by archiving change 2026-06-02-agent-statistics-panel. Update Purpose after archive.
## Requirements
### Requirement: Drill from user to request list

The system SHALL let an admin drill from the per-user ranking to a user's request list, filterable by time / agent / channel, with each entry showing time, input summary, token usage, elapsed, and result status.

#### Scenario: User drills to their request list
- **WHEN** an admin selects user Alice in `ops-bot`'s per-user view and clicks her
- **THEN** Alice's request list for that agent (or all agents) is shown, filterable by time / channel
- **AND** each row shows time, input summary, tokens, elapsed, and result status

### Requirement: Single-request full event stream

The system SHALL render a single request as a time-ordered event stream: user input, each LLM round (model / tokens / elapsed / whether fallback was triggered), each tool call's input / output / elapsed / success-failure, permission_gate decisions, memory hits, context-compression events, and the final reply. Each node SHALL be expandable / collapsible and its raw JSON copyable. The view SHALL render strictly from emitted trace events and SHALL NOT emit or generate any correlation IDs itself.

#### Scenario: Event stream for a request
- **WHEN** an admin opens the full-trace view for one of Alice's requests
- **THEN** the stream shows, in time order, user input, each LLM round (model / tokens / elapsed / fallback), each tool call's input and output, permission_gate decisions, memory hits, compression events, and the final reply

#### Scenario: Node expand and copy raw JSON
- **WHEN** an admin expands a node and copies its raw JSON
- **THEN** the copied JSON is the already-redacted trace payload for that event

#### Scenario: Panel renders, does not emit
- **WHEN** the request-trace view assembles a request's stream
- **THEN** it reads existing trace events by `request_id` and does not create, mutate, or emit any trace events or correlation IDs

### Requirement: Request correlation by request_id

The system SHALL assemble a request's event stream by grouping trace events that share the same `request_id` (emitted by agent-runtime / observability), ordered by timestamp ascending.

#### Scenario: Group events by request_id
- **WHEN** a run carries a `request_id` and emits LLM, tool, approval, memory, and compression events under it
- **THEN** the request-trace view groups all of them under one request, ordered by ts ascending

### Requirement: Sub_agent subtree expansion

When a request derives a sub_agent (inheriting the parent `request_id` with its own `span_id`, and linkable via `parent_session_id`), the system SHALL allow expanding the sub_agent node in place to show its complete sub-chain, structured identically to the parent chain.

#### Scenario: Expand sub_agent sub-chain in place
- **WHEN** a request derived a sub_agent during its run and the admin clicks the sub_agent node
- **THEN** the sub_agent's complete sub-chain is expanded in place via `parent_session_id`, structured the same as the parent chain

### Requirement: Session-level degradation when request_id is missing

When a run has no `request_id` (e.g. an older HTTP trace, not backfilled), the system SHALL degrade to available correlation keys (`session_id`, or `ts` + `user_id` window) to best-effort assemble the request, SHALL show a notice that the request lacks complete correlation keys and the chain may be incomplete, and SHALL NOT error.

#### Scenario: Degrade to session-level correlation
- **WHEN** a run carries no `request_id` and the admin opens its request-level view
- **THEN** the view degrades to `session_id` / `ts` + `user_id` to best-effort aggregate the chain
- **AND** shows a notice that the request lacks complete correlation keys and the chain may be incomplete
- **AND** does not raise an error

#### Scenario: Sub_agent linkage under degradation
- **WHEN** under degradation a sub_agent is still linkable by `parent_session_id`
- **THEN** its sub-chain is expanded; otherwise the node degrades to an "unable to link sub-chain" notice rather than erroring

