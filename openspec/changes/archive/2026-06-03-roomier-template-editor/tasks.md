## 1. Themed, roomy editor

- [x] 1.1 Write failing tests (tests/integration/test_admin_console_ui.py): global form-control CSS rule includes `textarea`; template modal-box is `wide`; `tmpl-system-prompt` textarea has a larger row count (>= 12)
- [x] 1.2 In admin.html: add `textarea` to the `input, select` style rule (plus `width:100%; box-sizing:border-box; resize:vertical;`); add the `wide` class to the template modal-box; raise `tmpl-system-prompt` rows → tests green

## 2. Gate + finalize

- [x] 2.1 Run `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src`
- [x] 2.2 Run full suite `uv run pytest -x -q` → all green
