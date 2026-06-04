# Agents and Templates as in-page sub-tabs

## Why

The previous change split templates into a separate sidebar nav item. The
intended UX is different: keep a single **Agents** sidebar item and surface
**Agents** / **Templates** as two sub-tabs inside the Agents page header (the
area next to the page title). This keeps templates within the Agents module
while still separating the two lists.

## What Changes

- Remove the separate **Templates** sidebar nav item and its `#tab-templates`
  section.
- Inside the Agents page, add a sub-tab switcher (Agents | Templates) in the
  page header; selecting a sub-tab shows its pane (agent list vs template
  list) within the same `#tab-agents` section.
- Wire the sub-tab switch to lazy-load the template list on first view; the
  Refresh button refreshes the active sub-tab.

Pure-frontend (admin.html) change; no API or data changes.

## Impact

- Affected specs: `agent-admin-ui` (MODIFIED: template editing lives in an
  Agents-page sub-tab rather than a separate sidebar tab).
- Affected code: `src/fleetent/static/admin.html` only.
