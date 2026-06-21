## ADDED Requirements

### Requirement: Operator agent chat console in the React SPA

The React admin SPA SHALL provide an operator console to converse with / debug a managed agent: select an agent, send a message, and see the reply streamed. It SHALL call the platform ingress `POST /admin/agents/{name}/chat` with the admin session credential (Authorization header) and consume the response as an **SSE event stream** — `data:` lines carrying JSON events `{type, content}` where `type` is `text_delta` (append to the reply), `done` (finish the turn), or `error` (surface the message) — rendering text deltas incrementally as they arrive. When the target agent is unreachable, it SHALL show a clear message rather than hang: the ingress returns `404` (unknown agent) or `503` (no node placement), and an upstream `error` event SHALL be surfaced in the conversation.

#### Scenario: Operator chats with a managed agent

- **WHEN** an admin selects an agent, types a message, and sends
- **THEN** the SPA calls `POST /admin/agents/{name}/chat` with the admin credential and renders the agent's reply as it streams in

#### Scenario: Streamed reply renders incrementally via SSE events

- **WHEN** the agent's reply arrives as SSE `data:` events (`text_delta` chunks then `done`)
- **THEN** the console parses each event and appends `text_delta` content as it arrives (not only after the full response completes), finishing the turn on `done`

#### Scenario: Upstream error event is surfaced

- **WHEN** the stream carries an `error` event (e.g. the agent's model call fails)
- **THEN** the console shows that error in the conversation rather than silently dropping it

#### Scenario: Unreachable agent shows a clear message

- **WHEN** the selected agent is unknown (ingress `404`) or has no node placement (ingress `503`)
- **THEN** the console shows a clear "agent unavailable" message and does not hang or spin indefinitely

#### Scenario: Agent selection uses the existing list

- **WHEN** the operator opens the chat console
- **THEN** selectable agents come from `GET /admin/agents`
