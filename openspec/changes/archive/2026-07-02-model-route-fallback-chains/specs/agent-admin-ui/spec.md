## MODIFIED Requirements

### Requirement: Model route selectors cover all standard routes

The agent detail view SHALL expose model routing on a dedicated **Models** tab (separate from the
overview tab), covering every standard model route key exposed by the runtime (`default`,
`memory_extraction`, `kb_extraction`, `vision`, `embedding`, `rerank`, `image_generation`,
`audio_transcription`, `audio_generation`). The tab SHALL present a **two-level model policy**:

- **Model tiers** — three fixed, system-defined slots (`primary`, `fast`, `backup`) private to the
  agent. An admin assigns at most one registry model to each slot and MAY override `temperature`
  and `max_tokens` per slot (blank = inherit the model's registered default). The admin SHALL NOT be
  able to rename or add tier slots. Assignments persist to `model_overrides.targets[<tier>]` as
  `{model_id, max_tokens?, params?}`; a slot with no model writes nothing, and when no slot has a
  model the `targets` block is omitted entirely.
- **Route chains** — for each route key, an **ordered fallback chain** of one or more entries
  (primary first, then fallbacks in priority order), each with optional `temperature` / `max_tokens`
  overrides. The **chat routes** (`default`, `memory_extraction`, `kb_extraction`, `vision`)
  reference the agent's tiers: each entry is `{target: <tier>}` and its candidate list is the
  assigned tiers. The **specialized routes** (`embedding`, `rerank`, `image_generation`,
  `audio_transcription`, `audio_generation`) reference registry models directly: each entry is
  `{model_id, max_tokens?, params?}` and its candidate list is filtered by the route's runtime
  protocol(s) (read from each model's `protocol` in `GET /admin/models`). Within one chain a
  tier/model already chosen earlier SHALL be excluded from the remaining entries' candidates.

The tab SHALL persist through the existing `PATCH /admin/agents/{name}` `model_overrides` path
(`routes[<route_key>]` as the ordered entry list, `targets[<tier>]` for tier definitions) without
introducing a new API field, and SHALL never persist an empty list for a route (an emptied chain
removes the route key so it falls back to the platform default). Configuration SHALL round-trip:
re-reading `GET /admin/agents/{name}` SHALL prefill each tier slot from `model_overrides.targets`
and each chain from `model_overrides.routes`, including a legacy single-entry override read back as
a one-element chain. All editing controls SHALL be hidden from / read-only for viewers.

#### Scenario: Admin assigns tiers and references them as a chat-route fallback chain
- **WHEN** an admin assigns models to the `primary` and `backup` tiers, then on the `default` (chat)
  route picks `primary` and adds `backup` as a fallback, and saves
- **THEN** the SPA calls `PATCH /admin/agents/{name}` with `model_overrides.targets` holding the two
  tier definitions and `model_overrides.routes.default` as the ordered list
  `[{target: "primary"}, {target: "backup"}]`, and re-opening the tab prefills both tiers and the
  chain in order

#### Scenario: Admin configures a specialized-route chain with a per-entry override
- **WHEN** an admin adds a second (fallback) model to a specialized route, sets its temperature, and
  saves
- **THEN** the SPA calls `PATCH /admin/agents/{name}` with `model_overrides.routes[<route_key>]` as an
  ordered two-entry list of `{model_id, ...}` whose second entry carries `params.temperature`, and
  re-opening the tab prefills both entries in order

#### Scenario: Per-tier temperature override
- **WHEN** an admin assigns a model to a tier slot, expands its override controls, sets a
  temperature, and saves
- **THEN** `model_overrides.targets[<tier>]` is `{model_id, params: {temperature}}`

#### Scenario: Reordering a chain changes fallback priority
- **WHEN** an admin reorders the entries of a route's chain and saves
- **THEN** the persisted `model_overrides.routes[<route_key>]` list order matches the new on-screen
  order (which the runtime consumes as fallback priority)

#### Scenario: Emptying a route's chain
- **WHEN** an admin removes the last entry from a route and saves
- **THEN** the route key is omitted from `model_overrides.routes` (never written as an empty list),
  and the runtime resolves that route to its baseline default

#### Scenario: Reserved audio route with no supported model
- **WHEN** an admin opens the Models tab and no registered model matches an audio route's protocol
  filter (`audio_transcription` / `audio_generation`)
- **THEN** that route shows an empty chain with an explicit hint that no model supports the route
  yet, and leaving it empty writes nothing to `model_overrides` for that route

#### Scenario: Route selector protocol filtering
- **WHEN** an admin opens any entry's model selector for the `rerank` route
- **THEN** only models whose `protocol` is `http_rerank` are offered, and chat-only models are excluded

#### Scenario: Single-model specialized route stays a one-entry chain
- **WHEN** an admin picks exactly one model for a specialized route (no fallback, no overrides) and
  saves
- **THEN** `model_overrides.routes[<route_key>]` is a single-entry list `[{model_id}]`, unchanged from
  the pre-fallback behavior
