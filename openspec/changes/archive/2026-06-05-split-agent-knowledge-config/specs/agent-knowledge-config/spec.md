## ADDED Requirements

### Requirement: Agent knowledge bindings

`agent.yaml` SHALL define Agent-side knowledge access under `knowledge`, not under
`knowledge_base`. The Agent-side config SHALL contain bindings to KB ids and retrieval policy,
but SHALL NOT contain KB source connector construction details such as Google Drive folders or
Confluence spaces.

#### Scenario: Agent binds to one or more KBs
- **WHEN** an Agent config declares `knowledge.enabled: true`
- **THEN** it must declare at least one `knowledge.bindings[]` entry with `tenant_id` and `kb_id`

#### Scenario: Agent has one default KB at most
- **WHEN** multiple `knowledge.bindings[]` entries are declared
- **THEN** at most one entry may have `default: true`

#### Scenario: Old source connector nesting is not accepted
- **WHEN** an Agent config declares `knowledge_base.google_drive.connectors[]` or
  `knowledge_base.confluence.connectors[]`
- **THEN** Agent config loading fails loudly

### Requirement: Agent retrieval policy

Agent-side `knowledge.retrieval_policy` SHALL define how the Agent queries bound KBs. It MAY
include retrieval mode, top_k, rerank enablement, and model route references for embedding/rerank.

#### Scenario: Hybrid retrieval policy
- **WHEN** `retrieval_policy.mode` is `hybrid`
- **THEN** the Agent retrieval path uses hybrid KB search over the bound KBs

#### Scenario: Model routes are referenced by route key
- **WHEN** `retrieval_policy.embedding_route` or `retrieval_policy.rerank_route` is set
- **THEN** the value references a route key from the Agent model policy
- **AND** this spec treats the value as an opaque route-key string until Agent-scoped model routing
  wires model resolution

### Requirement: Agent retrieval is scoped by bindings

Agent KB retrieval SHALL be limited to the KBs declared in `knowledge.bindings[]`.

#### Scenario: Unbound KB is not queried
- **WHEN** an Agent is bound only to `support-kb`
- **THEN** retrieval does not query `billing-kb`
