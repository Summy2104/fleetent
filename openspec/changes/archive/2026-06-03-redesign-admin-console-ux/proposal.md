## Why

The admin console (`admin.html`) grew to 13 modules across 8 management domains, but its shell stayed at the original prototype level: a 1100px box, a cramped two-level top tab bar, raw borderless tables, inline styles, and native `alert()`/`confirm()` dialogs with no toasts, empty states, or loading feedback. Wide modules (Stats, Sessions) overflow horizontally and the whole surface reads as unpolished. Now that all domains are wired, the shell is the bottleneck to a usable operator experience.

## What Changes

- **BREAKING (DOM/CSS only)**: Replace the top group/tab bar with a fixed left **sidebar** (grouped sections → module items) plus a right content area. The `switchGroup()` / `switchTab()` JS contract and all `data-group`/`data-tab` markers are preserved so existing behavior and UI-marker tests do not regress.
- Add a **design-token layer** (`:root` custom properties for color scale, spacing, radius, typography, elevation) and refine the dark theme for hierarchy and contrast.
- Introduce reusable **UI primitives**: page header (title + actions + filter slot), polished data table (sticky header, zebra/hover, horizontal scroll container), card, **toast** notifications, app-level **confirm dialog**, **empty state**, and **loading state** — replacing native `alert()`/`confirm()` and bare tables.
- Make the layout **responsive** (collapsible sidebar on narrow widths) and apply **basic a11y** (focus styles, aria labels on nav/dialogs, keyboard-dismissable modals).
- Keep role-gating (viewer hides write controls) and secret masking (password fields, no prefill) intact under the new components.

Non-goals: no backend changes, no new endpoints, no framework/build step, no new dependencies — stays a single self-contained vanilla-JS file reusing `/admin/*` and `api()`.

## Capabilities

### New Capabilities
- `admin-console-design-system`: The admin console's visual/interaction shell — sidebar navigation layout, design tokens, and reusable UI primitives (page header, table, toast, confirm dialog, empty/loading states) that all module panels render through.

### Modified Capabilities
<!-- none: existing *-admin-ui capabilities describe per-module wiring/endpoints, which are unchanged. This change only restructures the shell and styling those panels live in. -->

## Impact

- `src/fleetent/static/admin.html` — `<style>` block (token layer + component CSS), `<body>` shell (sidebar + content), and the nav/dialog JS (`switchGroup`/`switchTab` render path, new `toast()`/`confirmDialog()` helpers replacing `alert()`/`confirm()`).
- `tests/integration/test_admin_console_ui.py` — existing 36 markers must stay green; new markers for sidebar/page-header/toast/tokens added.
- No backend, DB, or dependency impact.
