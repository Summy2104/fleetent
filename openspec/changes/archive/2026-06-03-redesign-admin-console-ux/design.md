## Context

`admin.html` is a single self-contained vanilla-JS SPA. Today: `<style>` (lines 7–60) holds prototype CSS with a narrow `.wrap` (max 1100px), top `.groups` + `.tabs` bars; `<body>` has `login-view` / `reset-view` / `app-view` with a `header` and 13 `<section id="tab-*">` blocks. JS exposes `switchGroup(group)` + `switchTab(tab)` driven by `TAB_GROUP` / `GROUP_DEFAULT_TAB` maps and a `LOADERS` registry; module panels render raw `<table>` and use native `alert()` / `confirm()`. Role gating in `enterApp()` hides write controls for viewers; secret fields are `type=password` and never prefilled.

This change restructures the shell (layout, tokens, primitives) without touching backend, the `/admin/*` API calls, the `api()` helper, or the per-module wiring/endpoints. The `switchGroup`/`switchTab` contract and `data-group`/`data-tab` markers stay so the 36 existing UI-marker tests and all module behavior keep working.

## Goals / Non-Goals

**Goals:**
- Fixed left sidebar (grouped sections → module items) + right content area; collapsible on narrow widths.
- Centralized design tokens; refined dark theme (hierarchy, contrast, accent).
- Reusable primitives: page header, data table (sticky header, hover, horizontal scroll), card, toast, in-app confirm dialog, empty state, loading state.
- Replace native `alert()`/`confirm()` with `toast()` / `confirmDialog()`.
- Preserve role gating + secret masking under new components.
- Basic a11y: focus styles, aria on nav/dialogs, Esc to close modals.

**Non-Goals:**
- No backend/endpoint/DB changes; no new dependencies; no framework/build step (stays single-file vanilla JS).
- No rewrite of per-module data flows or endpoint paths (only the rendering shell + shared helpers change).
- Not a light/dark theme toggle (dark refined only this change).
- No full SSE streaming UI (unchanged from prior decision).

## Decisions

**D1: Sidebar replaces top tab bars; JS contract preserved.**
Render groups + module items as a `<nav class="sidebar">`; keep `data-group`/`data-tab` attributes on the items. `switchGroup`/`switchTab` keep their signatures and the `TAB_GROUP`/`GROUP_DEFAULT_TAB`/`LOADERS` maps; only the active-class toggling targets sidebar items instead of `.groups`/`.tabs` buttons. Alternative: flat sidebar of 13 items (rejected — grouping is the established IA). This keeps existing marker tests (`switchGroup(`, `data-group=`, `data-tab=`) green.

**D2: Token layer.**
Expand `:root` to a token set: color scale (`--bg-0..2`, `--surface`, `--border`, `--text`, `--text-muted`, `--accent`, `--danger`, `--ok`, `--warn`), spacing (`--sp-1..6`), radius (`--r-1..3`), type, elevation (`--shadow-1..2`). Components reference tokens only.

**D3: Primitives as CSS classes + tiny JS helpers, no templating engine.**
`.page-header`, `.data-table` (wrapped in `.table-scroll`), `.card`, `.empty`, `.loading`/skeleton, `.toast`/`#toast-host`, `.confirm` dialog. Helpers: `toast(msg, kind)` appends to `#toast-host` and auto-dismisses; `confirmDialog(msg)` returns a Promise<boolean> rendered via the modal pattern. Reuse existing `.modal`/`.menu` patterns where possible.

**D4: Migrate call sites incrementally but completely.**
Replace `alert(...)` → `toast(...)`; replace `if(!confirm(...))return;` → `if(!(await confirmDialog(...)))return;` (handlers already `async`). Wrap each module's table in `.table-scroll`; route list renders through a shared `renderTable`/empty/loading path where cheap, otherwise add empty/loading inline. Keep edits minimal per module to limit regression risk.

**D5: Role gating + secrets unchanged in logic.**
`enterApp()` viewer-hide loop and `IS_VIEWER` gating stay; only the hidden containers' markup moves into the new shell. Secret fields remain `type=password autocomplete=off`, never prefilled.

**D6: TDD via UI-marker tests.**
Extend `tests/integration/test_admin_console_ui.py`: assert sidebar structure (`class="sidebar"`, nav items carry `data-tab`), `page-header`, `toast`/`#toast-host`, `confirmDialog`, token presence (e.g. `--surface`, `--sp-`), `table-scroll`, `empty`/`loading`. Existing 36 assertions must stay green (do not weaken them). Browser-verify each module renders, navigates, and that a toast + confirm dialog appear.

## Risks / Trade-offs

- [Large single-file diff] → high churn in one file; mitigate by preserving JS contract and migrating call sites mechanically, module-by-module, re-running tests after each.
- [Regression in existing 36 markers] → keep `switchGroup`/`switchTab`/`data-*` exactly; tests act as the guardrail.
- [alert/confirm → async confirmDialog timing] → handlers are already async; ensure every former `confirm()` call site `await`s `confirmDialog()` so destructive actions still gate.
- [Scope creep into per-module behavior] → explicitly limit edits to shell + shared helpers + table-wrapping; no endpoint/logic changes.
- [a11y/responsive partial] → "basic" only; full WCAG audit is out of scope.

## Migration Plan

1. Add token layer + component CSS (additive; old classes can coexist during transition).
2. Build the sidebar shell + page-header scaffold; rewire `switchGroup`/`switchTab` active-class targets; verify existing markers + browser nav.
3. Add `toast()` / `confirmDialog()` + hosts; migrate all `alert()`/`confirm()` call sites.
4. Wrap module tables in `.table-scroll`; add empty/loading states.
5. Responsive + a11y pass.
6. Remove dead prototype CSS; run ruff/mypy/full pytest + browser smoke per module.
Rollback = revert admin.html (and the test additions). No DB migration.
