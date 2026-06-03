## 1. Tab persistence

- [x] 1.1 Write failing tests (tests/integration/test_admin_console_ui.py): `switchTab` writes `location.hash`; app entry restores tab from hash with a `users` fallback (assert on the markup/JS, e.g. `location.hash` set in `switchTab`, hash read on enter, fallback to `"users"`)
- [x] 1.2 In admin.html: set `location.hash = tab` in `switchTab()`; replace the hardcoded `switchTab("users")` on app entry with a restore-from-hash helper that validates against `TAB_GROUP` and falls back to `users` → tests green

## 2. Gate + finalize

- [x] 2.1 Run `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src`
- [x] 2.2 Run full suite `uv run pytest -x -q` → all green
