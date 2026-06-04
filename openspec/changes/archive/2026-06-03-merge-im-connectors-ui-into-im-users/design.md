## Context

`admin.html` is a self-contained vanilla-JS SPA. Navigation is data-driven:
- `TAB_GROUP` maps a tab id → nav group; `GROUP_DEFAULT_TAB` maps a group → its first tab.
- `switchTab(tab)` toggles `.nav-item`/`.nav-group-label` active state and shows the single matching `section#tab-<tab>`, then calls `LOADERS[tab]` if registered.
- Today: tab `im` (section `#tab-im`, group `access`, `LOADERS.im = loadIm`) and tab `connectors` (section `#tab-connectors`, group `models`, `LOADERS.connectors = loadConn`).

Connector UI machinery to preserve: `loadConn`, `conn-body`, `conn-create-bar` (viewer-gated), `openConnModal`/`createConn`/`renderConnFields`/`connEnable`/etc., and the owner column added by `user-scoped-im-connectors`.

## Goals / Non-Goals

**Goals:**
- One IM tab under Access showing IM-users block + connectors block on one page.
- Remove the standalone `connectors` nav item and `#tab-connectors` section.
- Preserve every connector + IM-user action and its endpoint.

**Non-Goals:**
- No backend/route/API change.
- No redesign of the connector table, modal, or credential masking.
- No change to viewer gating rules.

## Decisions

**D1 — Fold connectors content into `#tab-im`, keep two visual blocks.**
The `#tab-im` section gets two `page-header` blocks: IM Users (existing table) then IM Connectors (relocated table + `conn-create-bar` + modal trigger). Rationale: matches the user's "show together on one page" choice; minimal JS churn — only nav/section/loader wiring moves, render functions are untouched. Alternative (segmented sub-tabs) rejected: more JS, not requested.

**D2 — Drive both lists from `LOADERS.im`.**
`LOADERS.im = () => { loadIm(); loadConn(); }`. Remove `LOADERS.connectors` registration and the `connectors` entry from `TAB_GROUP`. Rationale: opening the single tab must refresh both blocks. The modal trigger keeps calling `openConnModal()` directly.

**D3 — Remove the `connectors` nav item and `#tab-connectors` wrapper only.**
Delete the `<button … data-tab="connectors" …>` from the Models & Connectors group and unwrap `#tab-connectors`, moving its inner markup into `#tab-im`. `switchTab` needs no change — it already shows one section and iterates `section[id^='tab-']`; a stale `connectors` tab id simply ceases to exist.

## Risks / Trade-offs

- [Existing UI marker tests assert a separate `connectors` tab] → Update `test_admin_console_ui.py`: drop `connectors` from the reachable-tab lists, add assertions that `#tab-connectors`/`data-tab="connectors"` are gone and that connector markers (`conn-body`, `conn-create-bar`, `loadConn`, owner column) live inside `#tab-im` and `LOADERS.im` triggers `loadConn`. TDD: write these first (red).
- [Deep-links/bookmarks to the connectors tab] → No router/hash navigation exists in the SPA (default `switchTab("users")` on load), so no broken links.
- [Page length grows on the IM tab] → Acceptable; both tables already sit in `table-scroll` containers.

## Migration Plan

Pure static-asset edit. Deploy = ship updated `admin.html`. Rollback = revert the file. No data or API migration.
