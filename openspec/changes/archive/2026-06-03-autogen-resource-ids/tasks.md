## 1. Auto-generated read-only ids

- [x] 1.1 Write failing tests (tests/integration/test_admin_console_ui.py): a `genId` helper exists; the four id inputs (`tmpl-id`, `nkb-id`, `pv-id`, `oc-id`) are `readonly` in the markup; create flows call `genId()` to fill the id
- [x] 1.2 In admin.html: add `genId()`; mark the four id inputs `readonly`; fill the id with `genId()` when each create form opens (template/provider/connector) and prefill `nkb-id` for KB create + regenerate after create → tests green

## 2. Gate + finalize

- [x] 2.1 Run `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src`
- [x] 2.2 Run full suite `uv run pytest -x -q` → all green
