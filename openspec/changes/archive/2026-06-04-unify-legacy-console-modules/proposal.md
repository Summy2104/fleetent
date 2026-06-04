## Why

The admin console now has two visual systems. Users, Agents, Skills, Providers and Connectors use the modern toolbar with a search box; Knowledge Base, Sessions, Monitoring and Statistics still use the legacy `page-header` + table layout whose `.ph-filter` slot is rendered but left empty, so they ship with **no search at all** — only a Refresh button. On long lists (sessions, per-user stats, alerts, knowledge bases) the operator has no way to narrow down what they see, and the inconsistency makes the console feel unfinished. The design system already promises a "filter/search slot" in every page header; these four modules don't honor it.

## What Changes

- Fill the empty `.ph-filter` slot in the four legacy modules (Knowledge Base, Sessions, Monitoring, Statistics) with a search input that filters the already-rendered rows client-side, by the obvious fields per module:
  - Knowledge Base: kb_id / description
  - Sessions: session id / user / agent
  - Monitoring: alert + metric name
  - Statistics: user (id / name / email)
- Keep each module's existing data, columns, actions, and endpoints untouched — this only adds the search/consistency layer.
- Ensure each module shows a clear empty state when a search yields no rows (consistent with the design system's empty-state requirement).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `admin-console-design-system`: the page-header filter/search slot becomes a stated requirement for list/table modules — they MUST expose a working row search, and the four named legacy modules must conform.

## Impact

- Frontend only: `src/fleetent/static/admin.html` (markup for the four `#tab-*` sections + their render functions).
- Tests: assertions added to `tests/integration/test_admin_console_ui.py`.
- No backend, API, schema, or dependency changes.
