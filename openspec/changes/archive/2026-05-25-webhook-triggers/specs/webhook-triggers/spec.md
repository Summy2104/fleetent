## ADDED Requirements

### Requirement: Webhook source configuration
The system SHALL load webhook source definitions from `config/webhooks.yaml` at startup. Each source SHALL have a unique `id` and a `user_id` referencing a valid internal user. `secret`, `agent_name`, and `message_template` are optional. If the file does not exist, the webhook feature SHALL be silently disabled.

#### Scenario: Valid config loaded at startup
- **WHEN** `config/webhooks.yaml` exists with at least one source entry
- **THEN** `POST /webhook/{source_id}` routes are available for each configured source id

#### Scenario: Missing config file does not crash
- **WHEN** `config/webhooks.yaml` does not exist
- **THEN** the server starts successfully and webhook routes return 404

### Requirement: Webhook endpoint accepts POST requests
`POST /webhook/{source_id}` SHALL accept a JSON body from any caller. The endpoint SHALL return 202 Accepted immediately. If `source_id` is not found in the loaded configuration, the endpoint SHALL return 404.

#### Scenario: Known source returns 202
- **WHEN** `POST /webhook/github-ci` is called with a valid JSON body and the source is configured
- **THEN** the response status is 202

#### Scenario: Unknown source returns 404
- **WHEN** `POST /webhook/nonexistent-source` is called
- **THEN** the response status is 404

### Requirement: HMAC-SHA256 signature verification
When a webhook source has a `secret` configured, the system SHALL verify the `X-Hub-Signature-256` header against the request body using HMAC-SHA256. Requests with a missing or invalid signature SHALL be rejected with 403.

#### Scenario: Valid signature accepted
- **WHEN** the request includes `X-Hub-Signature-256: sha256=<valid_hmac>` matching the body and secret
- **THEN** the request is accepted and returns 202

#### Scenario: Invalid signature rejected
- **WHEN** the request includes a signature header that does not match the computed HMAC
- **THEN** the response status is 403

#### Scenario: Missing signature header rejected
- **WHEN** the source has a secret configured but the request has no `X-Hub-Signature-256` header
- **THEN** the response status is 403

#### Scenario: No secret configured skips verification
- **WHEN** the source has no `secret` configured
- **THEN** the request is accepted regardless of whether a signature header is present

### Requirement: Payload text extraction via message template
When a source has a `message_template` configured, the system SHALL extract the message text by substituting payload fields using Python `str.format_map`. When `message_template` is absent or substitution fails, the system SHALL fall back to `json.dumps(payload)`.

#### Scenario: Template substitution succeeds
- **WHEN** `message_template` is `"PR merged: {repository[name]}"` and payload contains `{"repository": {"name": "mini-agent"}}`
- **THEN** the extracted message text is `"PR merged: mini-agent"`

#### Scenario: Template substitution fails gracefully
- **WHEN** `message_template` references a field not present in the payload
- **THEN** the message text falls back to the full JSON-serialized payload without raising an error

### Requirement: Agent run dispatched as background task
After accepting the webhook request, the system SHALL construct a `NormalizedMessage` and dispatch it to `normalizer.route()` as an asyncio background task. The HTTP response SHALL NOT wait for the agent run to complete.

#### Scenario: Background task dispatched
- **WHEN** a valid webhook request is received
- **THEN** 202 is returned immediately and the agent run starts asynchronously

#### Scenario: Session persistence per source
- **WHEN** multiple webhook events arrive from the same source
- **THEN** they share the same session (`session_id = "webhook-{source_id}"`), giving the agent cross-event context

### Requirement: Webhook reply is a no-op
The `reply_func` passed to `normalizer.route()` for webhook-triggered runs SHALL be a no-op async function. The agent run result SHALL be recorded in eval trace only; no outbound message is sent.

#### Scenario: reply_func is no-op
- **WHEN** the agent run completes after a webhook trigger
- **THEN** no outbound HTTP call or IM message is sent; the result appears in eval trace
