## ADDED Requirements

### Requirement: Model route selectors cover all standard routes

The agent detail view SHALL expose model routing on a dedicated **Models** tab (separate from the
overview tab), rendering a model selector for every standard model
route key exposed by the runtime (`default`, `memory_extraction`, `kb_extraction`, `vision`,
`embedding`, `rerank`, `image_generation`, `audio_transcription`, `audio_generation`). Each
selector SHALL filter its candidate models by the route's runtime protocol(s) (read from each
model's `protocol` in `GET /admin/models`), and SHALL persist the selection through the existing
`PATCH /admin/agents/{name}` `model_overrides.routes[<route_key>]` path without introducing a new
API field. Selections SHALL round-trip: re-reading `GET /admin/agents/{name}` SHALL prefill each
selector from `model_overrides.routes`. All selectors SHALL be hidden from / read-only for viewers,
consistent with the other overview fields.

#### Scenario: Admin selects a model for a newly exposed route
- **WHEN** an admin opens the overview tab, picks a model for the `vision`, `kb_extraction`, or
  `rerank` route (whose candidate list is filtered to that route's protocol), and saves
- **THEN** the SPA calls `PATCH /admin/agents/{name}` with the selection folded into
  `model_overrides.routes[<route_key>]`, and re-opening the tab prefills that route's selector from
  the persisted `model_overrides`

#### Scenario: Reserved audio route with no supported model
- **WHEN** an admin opens the overview tab and no registered model matches an audio route's
  protocol filter (`audio_transcription` / `audio_generation`)
- **THEN** that route's selector is shown with an empty candidate list and an explicit hint that no
  model supports the route yet, and leaving it unset writes nothing to `model_overrides` for that
  route (the runtime keeps resolving the route to its baseline default)

#### Scenario: Route selector protocol filtering
- **WHEN** an admin opens the `rerank` route selector
- **THEN** only models whose `protocol` is `http_rerank` are offered as candidates, and chat-only
  models are excluded
