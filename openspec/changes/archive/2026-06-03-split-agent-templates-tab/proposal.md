# Split agent templates into their own tab

## Why

Agent templates currently live inside the Agents tab behind a "Templates"
toggle that reveals an inline panel above the agent list. This crowds the
Agents tab and hides template management behind an extra click. Agents and
templates are distinct concepts (templates are creation presets; agents are
live, versioned definitions) and deserve sibling tabs under the Agents group.

## What Changes

- Add a "Templates" nav item under the "Agents & Skills" group, with its own
  `#tab-templates` section.
- Move the template list, create bar, and modal out of the Agents tab into the
  Templates tab.
- Replace the `tmplToggle()` show/hide panel with a `LOADERS.templates` lazy
  loader (consistent with other tabs).
- Remove the "Templates" toggle button from the Agents tab action bar.

Pure-frontend (admin.html) change; no API or data changes.

## Impact

- Affected specs: `agent-admin-ui` (MODIFIED: template editing now lives in a
  dedicated Templates tab rather than an inline Agents-tab panel).
- Affected code: `src/fleetent/static/admin.html` only.
