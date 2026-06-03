# Auto-generate resource ids in admin create forms

## Why

Several admin create forms ask the user to type a unique resource `id`
(agent template, knowledge base, model provider, OAuth connector). Hand-typed
ids are error-prone (collisions, bad characters) and add friction. The id is an
internal key, not something the user needs to author. The user should not edit
it; the console should generate it.

## What Changes

- Add a client-side `genId()` helper that returns a random short id.
- For the four create forms (`tmpl-id`, `nkb-id`, `pv-id`, `oc-id`), populate
  the id field with a generated value when the create form opens and make the
  field read-only so the user cannot edit it.
- Edit forms keep showing the existing id read-only (unchanged behavior).

Pure-frontend (admin.html) change; no API or data changes — the generated id is
sent through the same existing create endpoints.

## Impact

- Affected specs: `admin-console-design-system` (ADDED: system-generated
  resource ids in create forms).
- Affected code: `src/fleetent/static/admin.html` only.
