## MODIFIED Requirements

### Requirement: Webhook source configuration
Webhook sources SHALL NOT be loaded from YAML files. Runtime source management is out of scope for
configuration-foundation and SHALL be handled by a later webhook source management change.

#### Scenario: Old webhook YAML is not loaded
- **WHEN** `config/webhooks.yaml` exists
- **THEN** server startup fails fast instead of loading webhook sources

#### Scenario: Missing webhook source returns 404
- **WHEN** no runtime source is registered for a source id
- **THEN** `POST /webhook/{source_id}` returns 404

### Requirement: Webhook global settings
Webhook trigger runtime SHALL read deployment-level policy from `config/settings.yaml`.

#### Scenario: Webhooks disabled
- **WHEN** `webhooks.enabled=false`
- **THEN** webhook endpoints reject requests without dispatching agent runs

#### Scenario: Max body size is configured
- **WHEN** request body size exceeds `webhooks.max_body_bytes`
- **THEN** the webhook endpoint rejects the request before dispatch
