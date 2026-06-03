## 0. Store: `Agent` carries all active-version fields

- [x] 0.1 Write failing tests (tests/integration/test_agent_store.py): `get_by_name` and `create_agent` return an `Agent` whose `skills_dir`/`mcp_server_ids`/`model_overrides`/`memory_namespace` reflect the active version
- [x] 0.2 Add the four fields (with defaults) to the `Agent` dataclass; unpack them in `get_by_name`; populate them on the `create_agent` return → tests green

## 1. Console API: create/read/update carry version-config fields

- [x] 1.1 Write failing tests (tests/integration/test_agent_console_api.py): create with skills_dir/mcp_server_ids/model_overrides/memory_namespace persists them on active version; GET returns the four fields; PATCH overrides only provided field and inherits the rest; clone copies the four fields
- [x] 1.2 Extend `CreateBody`/`UpdateBody` with the four fields; extend `_def_response` to return them; forward them in create/patch routes (PATCH: only non-None → store, else `_UNSET`); extend clone to copy them; update `create_agent_def`/`update_agent_def` seam signatures + the test `_wire_real_store` helper → tests green

## 2. Server seam wiring

- [x] 2.1 Write failing tests (tests/integration/test_server.py): wired create persists the four fields via store; wired update creates a version overriding only provided fields
- [x] 2.2 Update `wire_agent_store_seams()` inner wrappers (`_console_create`/`_console_update`/`_apply_create`/`_apply_update`) to pass the four fields through, translating `None`→`_UNSET` on update; keep mypy clean → tests green

## 3. admin.html modal inputs

- [x] 3.1 Write failing UI assertion tests (tests/integration/test_admin_console_ui.py): modal contains `#ag-skills-dir`, `#ag-mcp-server-ids`, `#ag-model-overrides`, `#ag-memory-namespace`; agSave references them; agEdit prefills them
- [x] 3.2 Add the four inputs to `#ag-modal`; extend `agEdit` prefill from GET and `agSave` serialize (parse mcp_server_ids + model_overrides as JSON/array with inline error on bad input) → tests green

## 4. Gate + finalize

- [x] 4.1 Run `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src`
- [x] 4.2 Run full suite `uv run pytest -x -q` → all green
