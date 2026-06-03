## 1. Design tokens + base theme

- [x] 1.1 Write failing UI test: `:root` exposes design tokens (e.g. `--surface`, `--sp-`, `--r-`, `--shadow`) and base/component CSS references them (tests/integration/test_admin_console_ui.py)
- [x] 1.2 Add token layer to `<style>` + refine base element styles to use tokens; run pytest → green
- [x] 1.3 Browser-verify page still renders (login + app) with no console error

## 2. Sidebar shell (replaces top tabs)

- [x] 2.1 Write failing UI test: sidebar present (`class="sidebar"`), grouped sections + module items carry `data-group`/`data-tab`, all 13 modules reachable; existing nav markers (`switchGroup(`, `switchTab(`, `data-group=`, `data-tab=`) still asserted
- [x] 2.2 Rebuild `<body>` shell to sidebar + content; rewire `switchGroup`/`switchTab` active-class targets to sidebar items (keep maps + LOADERS); run pytest → green (incl. existing 36)
- [x] 2.3 Browser-verify: every group/module navigates via sidebar, active state correct, no console error

## 3. Page header primitive

- [x] 3.1 Write failing UI test: `page-header` class present with title + actions + filter slots used by modules
- [x] 3.2 Add `.page-header` component + apply to each module section header; run pytest → green
- [x] 3.3 Browser-verify: each module shows its title + primary actions

## 4. Toast + in-app confirm dialog

- [x] 4.1 Write failing UI test: `#toast-host`, `function toast`, `function confirmDialog` present; no remaining `alert(`/`confirm(` native calls in handlers
- [x] 4.2 Add `toast()`/`confirmDialog()` helpers + hosts; migrate all `alert()`/`confirm()` call sites (destructive actions `await confirmDialog`); run pytest → green
- [x] 4.3 Browser-verify: a success toast appears; a destructive action shows confirm dialog and only proceeds on confirm

## 5. Table + empty/loading states

- [x] 5.1 Write failing UI test: `table-scroll` wrapper, `empty` and `loading` state markers present
- [x] 5.2 Wrap module tables in `.table-scroll`; add empty + loading states to list renders; run pytest → green
- [x] 5.3 Browser-verify: a wide module (Stats/Sessions) scrolls horizontally; an empty list shows empty state; loading shows during fetch

## 6. Responsive + accessibility

- [x] 6.1 Write failing UI test: collapsible sidebar control + a11y markers (focus-visible style, `aria-label` on nav/dialog) present
- [x] 6.2 Add responsive sidebar collapse + focus styles + aria labels + Esc-to-close on modals; run pytest → green
- [x] 6.3 Browser-verify: narrow width collapses sidebar; Esc closes a modal; focus ring visible

## 7. Role gating + secrets regression

- [x] 7.1 Write failing UI test (if not already covered): viewer-hidden containers + password/no-prefill secret fields intact under new shell
- [x] 7.2 Confirm `enterApp()` viewer-hide loop covers all new/relocated write containers; secrets remain masked/no-prefill; run pytest → green
- [x] 7.3 Browser-verify: viewer login hides write controls; edit form leaves secret blank

## 8. Cleanup + gates

- [x] 8.1 Remove dead prototype CSS/markup no longer used
- [x] 8.2 `uv run ruff format src tests && uv run ruff check src tests`
- [x] 8.3 `uv run mypy src`
- [x] 8.4 Full `uv run pytest -q` green (incl. all admin_console_ui markers)
- [x] 8.5 Browser smoke: every module loads + navigates via sidebar without console error
