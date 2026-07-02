## MODIFIED Requirements

### Requirement: Provider CRUD and connectivity
The console SHALL let an admin create, edit, delete a provider and create, edit, delete a model under it, run a connectivity test on a model, and set per-model pricing, calling the matching `/admin/providers` and `/admin/models` endpoints. Deleting a referenced model or a provider that still has models SHALL surface the returned conflict (with referencing agents/routes) rather than silently failing. The model creation/edit form SHALL let an admin pick the model's protocol among `openai_chat`, `http_embedding`, `http_rerank`, and `openai_image_generation`, and SHALL render the connection field the chosen protocol requires (Base URL for `openai_chat`; Endpoint for the other three). All form labels and dialog text SHALL be localized (English/Chinese).

#### Scenario: Connectivity test on a model
- **WHEN** an admin runs a connectivity test on a model
- **THEN** the console calls the model-level connectivity-test endpoint and shows the result

#### Scenario: Guarded delete surfaces references
- **WHEN** an admin attempts to delete a model that is referenced by an agent route
- **THEN** the console surfaces the conflict naming the referencing agents/routes and does not remove the model

#### Scenario: Create a non-chat model
- **WHEN** an admin selects the `http_embedding` protocol while creating a model
- **THEN** the form shows an Endpoint field instead of Base URL, and the created model is submitted with `protocol: "http_embedding"` and `endpoint` set (no `base_url`)

#### Scenario: Model dialog text is localized
- **WHEN** an admin opens the New model dialog with the Chinese locale active
- **THEN** the dialog title, field labels, and buttons render in Chinese

### Requirement: Agent model routes are first-class in the console
The agent configuration UI SHALL let an admin independently configure the `default`, `embedding`, `memory_extraction`, and `image_generation` routes, each via its own single-select model picker. Each route's model selector SHALL be filtered by the protocol that route expects, so only protocol-compatible models are offered. Selecting a model SHALL write the route entry as a `model_id` reference (no inline connection fields). The `vision`, `kb_extraction`, and `rerank` routes are not exposed as independent bindings in the console; they continue to resolve to their platform default target when not explicitly overridden.

#### Scenario: Configure a non-default route
- **WHEN** an admin opens an agent's model routing and selects a model for the `embedding` route
- **THEN** the selector offers only `http_embedding` models, and saving writes `{model_id, ...}` under that route in `model_overrides`

#### Scenario: Protocol filtering prevents mismatch
- **WHEN** an admin opens the `embedding` route selector
- **THEN** chat-protocol models are not listed, so a chat model cannot be assigned to an embedding route

#### Scenario: Routes are configured independently
- **WHEN** an admin sets a model for the `embedding` route and saves, without touching the `default` or `memory_extraction` route selectors
- **THEN** the agent's `default` and `memory_extraction` routes are unaffected by the save
