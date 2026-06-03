# Tasks

## 1. Migration 035: template_id column

- [x] 1.1 Write failing test: upgrade head adds `template_id` to `agent_versions` (nullable)
- [x] 1.2 Add `migrations/versions/035_add_agent_version_template_id.py` (down_revision="034")

## 2. agent_store template_id threading

- [x] 2.1 Write failing tests: create_agent persists template_id; default NULL; new version inherits
- [x] 2.2 Add `template_id` to Agent + AgentVersion dataclasses; thread create_agent, _insert_version, _row_to_version, get_by_name, _merge_version_fields

## 3. server seam + console API

- [x] 3.1 Write failing tests: CreateBody requires template_id (422); unknown id 404; valid persists + GET echoes
- [x] 3.2 Add `template_id` to CreateBody (required) + _def_response; validate template exists in create route; thread _console_create + _agent_def_dict

## 4. admin.html New-agent modal

- [x] 4.1 Write failing UI test: ag-modal uses wide box; ag-template select required on create; agSave sends template_id
- [x] 4.2 Widen modal, add template select + prefill, block create without template, send template_id

## 5. Gate

- [x] 5.1 ruff format + check, mypy, full `uv run pytest -x -q`
