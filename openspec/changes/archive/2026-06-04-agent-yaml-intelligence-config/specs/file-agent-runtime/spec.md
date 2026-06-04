## ADDED Requirements

### Requirement: Agent file may carry intelligence configuration
The agent file model SHALL accept optional typed intelligence configuration blocks so the
deployed agent template can carry non-secret intelligence settings without requiring a
global settings template.

#### Scenario: Agent YAML accepts intelligence config blocks
- **WHEN** an `agent.yaml` declares `vector_store`, `embedding`, `rerank`,
  `knowledge_base`, and `long_term_ctx`
- **THEN** the agent file loads successfully
- **AND** those blocks are available as typed configuration objects on the loaded agent

#### Scenario: Intelligence config uses env references for secrets
- **WHEN** an `agent.yaml` declares real provider or connector configuration
- **THEN** API keys, OAuth credentials, and connector tokens are expressed as env-var
  reference field names
- **AND** no secret payload is required in the agent file

#### Scenario: Existing agent files remain valid
- **WHEN** an `agent.yaml` omits intelligence configuration blocks
- **THEN** the agent file loads with conservative typed defaults
- **AND** runtime behavior remains unchanged
