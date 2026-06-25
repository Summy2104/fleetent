## MODIFIED Requirements

### Requirement: Operator agent chat console in the React SPA

The React admin SPA SHALL provide an operator console to converse with / debug a managed agent: select an agent, send a message, and see the reply streamed. It SHALL call the platform ingress `POST /admin/agents/{name}/chat` with the admin session credential (Authorization header) and consume the response as an **SSE event stream** — `data:` lines carrying JSON events `{type, content}` where `type` is `text_delta` (append to the reply), `done` (finish the turn), or `error` (surface the message) — rendering text deltas incrementally as they arrive.

When the ingress returns a non-2xx HTTP response, the console SHALL surface the error's actual cause rather than hang or guess: it SHALL parse the response body's `detail` field (FastAPI `HTTPException` shape) and show that detail to the operator. When no `detail` is available (empty/non-JSON body), it SHALL fall back to a neutral, status-appropriate message that does NOT assert a specific cause. In particular, a `503` SHALL NOT be hardcoded as "no node placement" — `503` carries varied details (e.g. node service key unavailable, upstream stream failure, or genuinely no placement). An upstream `error` event in the SSE stream SHALL likewise be surfaced in the conversation.

#### Scenario: Operator chats with a managed agent

- **WHEN** an admin selects an agent, types a message, and sends
- **THEN** the SPA calls `POST /admin/agents/{name}/chat` with the admin credential and renders the agent's reply as it streams in

#### Scenario: Streamed reply renders incrementally via SSE events

- **WHEN** the agent's reply arrives as SSE `data:` events (`text_delta` chunks then `done`)
- **THEN** the console parses each event and appends `text_delta` content as it arrives (not only after the full response completes), finishing the turn on `done`

#### Scenario: Upstream error event is surfaced

- **WHEN** the stream carries an `error` event (e.g. the agent's model call fails)
- **THEN** the console shows that error in the conversation rather than silently dropping it

#### Scenario: Ingress error detail is surfaced

- **WHEN** the ingress returns a non-2xx response with body `{"detail": "node 'local-node' service key unavailable"}`
- **THEN** the console shows that detail to the operator (not a hardcoded "no active placement" message)
- **AND** it does not hang or spin indefinitely

#### Scenario: Neutral fallback when no detail is present

- **WHEN** the ingress returns a `503` with an empty or non-JSON body
- **THEN** the console shows a neutral status-appropriate "agent unavailable" message that does not assert a specific cause (e.g. does not claim "no node placement")

#### Scenario: Unknown agent shows a clear message

- **WHEN** the selected agent is unknown (ingress `404`)
- **THEN** the console shows a clear "agent not found" message and does not hang or spin indefinitely

#### Scenario: Agent selection uses the existing list

- **WHEN** the operator opens the chat console
- **THEN** selectable agents come from `GET /admin/agents`
