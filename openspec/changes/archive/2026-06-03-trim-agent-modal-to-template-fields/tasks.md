# Tasks

## 1. Trim agent modal fields

- [x] 1.1 Write failing UI test: agent modal has no skills_dir/mcp_server_ids/model_overrides/memory_namespace inputs; agSave omits them
- [x] 1.2 Remove the four inputs from ag-modal; drop their reads/writes in agCreate/agEdit/agSave

## 2. Gate

- [x] 2.1 ruff format + check, mypy, full `uv run pytest -x -q`
