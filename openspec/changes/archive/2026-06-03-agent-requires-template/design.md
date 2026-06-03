# Design

## Persisted template link lives on agent_versions

`template_id` is a per-version field, not an `agents` field, because the runtime
config it seeds (system_prompt/allowed_tools) already lives on `agent_versions`.
Recording the source template alongside the snapshot keeps provenance with the
config it produced. It is **nullable**: pre-existing rows and the apply path
(`agent_apply_api`) do not set it, and edits inherit `NULL` unless re-supplied.

Migration 035 adds the column with `down_revision = "034"`. No backfill — old rows
stay `NULL`.

## Threading

`agent_store.create_agent` gains a keyword `template_id: str | None = None`, written
by `_insert_version`. `Agent`/`AgentVersion` dataclasses gain `template_id`.
`get_by_name` reads it from the active version. `create_version`/`_merge_version_fields`
inherit `template_id` from the base version unless overridden (edit keeps the
original source template).

Server seam `_console_create` accepts and forwards `template_id`; `_agent_def_dict`
includes it so `_def_response` can echo it back.

## API contract

`CreateBody.template_id: str` (required — pydantic 422 if absent). The console route
validates the template exists via `agent_template_store.get_template`; unknown id →
404. `_def_response` adds `template_id` from the def dict. `UpdateBody` is untouched.

## UI

New-agent modal box becomes `wide`. A `<select id="ag-template">` is shown only in
create mode (hidden/ignored on edit). It is populated on open from
`GET /admin/agent-templates`. Changing it prefills `ag-system-prompt` and
`ag-allowed-tools`. `agSave` blocks create when no template chosen and sends
`template_id`.
