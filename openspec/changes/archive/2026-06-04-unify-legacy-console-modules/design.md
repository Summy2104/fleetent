## Context

The console's modern modules (Users/Agents/Skills/Providers/Connectors) render a toolbar with an `sk-search` input and filter rows in JS. The four legacy modules (KB/Sessions/Monitoring/Statistics) use the older `page-header` layout: title + `.ph-filter` slot (empty) + `.ph-actions` (Refresh). Their render functions build table rows from data already fetched into a module-level array (e.g. `ALL_*` / a render function that maps rows to `<tr>`). No backend changes are needed; the data is all client-side by render time.

## Goals / Non-Goals

**Goals:**
- Each legacy module gets a search input in its `.ph-filter` slot that filters the rendered rows by that module's identifying fields, live on input.
- Visual + interaction parity with the modern modules (reuse the existing `sk-search` styling).
- A no-match search shows the module's empty state, not a blank table.

**Non-Goals:**
- No backend/API/schema changes; search is client-side over already-loaded rows (no new query params).
- No conversion of these tables into card grids or drawers — keep tables, columns, and actions as-is.
- No new filter dimensions beyond a single free-text search (existing selects/period filters stay).

## Decisions

- **Client-side filter over the in-memory rows.** Each module already holds its rows (or can cache them at render time). Add a module search state var, an `<input class="sk-search">` in the `.ph-filter` slot, and have the render function filter rows by a lowercased substring match across the module's identifying fields before building `<tr>`s. Rationale: zero backend work, instant feedback, consistent with how Users/Agents already filter.
- **Cache the fetched rows.** Where a module renders directly from a fetch result without keeping it, store the rows in a module-level array (mirroring `ALL_USERS`/`ALL_AGENTS`) so the search can re-filter without re-fetching. Refresh refetches and repopulates the cache.
- **Reuse existing empty-state rendering.** The render already emits a "No X" row when there are no rows; a no-match filter produces an empty filtered list which hits the same path, so the empty state is consistent for free.
- **Per-module identifying fields** (search scope): KB → kb_id, description; Sessions → session id, user, agent; Monitoring → alert name, metric/source name (across its tables); Statistics → user id/name/email. Selects/period controls already present are left intact and compose with the text search.

## Risks / Trade-offs

- [Statistics/Monitoring have multiple tables] → the single search filters the primary list(s); document which table(s) it scopes and keep behavior obvious (filter the row-per-entity table, not summary tiles).
- [admin.html is large and shared; UI tests grep markup] → add assertions for each module's search input id + that its render function references the search value; keep existing nav/tab hooks.
- [Client-side only] → very large lists already paginate (Sessions/Users); the search filters the loaded set, consistent with current pagination behavior. Acceptable; noted, not a regression.
