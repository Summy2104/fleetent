## Context

fleetent's agent definition uses an immutable-snapshot model: `agents` + `agent_versions`. The per-version row carries `system_prompt`, `allowed_tools`, `skills_dir`, `mcp_server_ids`, `model_overrides`, `memory_namespace`. `agent_runtime.AgentSnapshot` (agent_runtime.py L30-47) is built from these and `agent_loop.py` (L734-763, 956-957, 1005-1057) consumes all six at runtime. `agent_store.create_agent` / `create_version` already accept and persist all six (create_version uses an `_UNSET` sentinel for partial overrides).

The recently-landed Agent CRUD (`complete-agent-crud-console`) exposed only `system_prompt` + `allowed_tools` through `POST/GET/PATCH /admin/agents` and the admin.html modal. The other four fields are runtime-active but unconfigurable from the console.

## Goals / Non-Goals

**Goals:**
- Carry `skills_dir`, `mcp_server_ids`, `model_overrides`, `memory_namespace` through create, read-full, and update endpoints + seams + server wiring.
- Surface them in the admin.html create/edit modal (admin-gated), prefilled on edit.
- Preserve immutable-snapshot semantics: PATCH overrides only provided fields; omitted fields inherit prior active version (use `_UNSET` passthrough).

**Non-Goals:**
- No DB migration (columns already exist).
- No runtime/agent_loop change (already consumes the fields).
- Do NOT add hermes-style NEW knobs (`max_turns`, `reasoning_effort`, `personalities`, memory toggles/char-limits, `session_reset`, `delegation` limits, `code_execution` limits). Those require a new `agent_versions` migration AND agent_loop wiring — tracked as future work below.

## Decisions

- **Field types in Pydantic bodies.** CreateBody: `skills_dir: str | None = None`, `mcp_server_ids: list[str] | None = None`, `model_overrides: dict[str, Any] = {}`, `memory_namespace: str = "default"` (matching `create_agent` defaults). UpdateBody: all four `| None = None`; on PATCH, only non-None fields are forwarded to `create_version`, leaving the rest as `_UNSET` so the prior snapshot value is inherited. (Note: `model_overrides={}` is a valid explicit clear on create; on PATCH a `None` means "leave unchanged".)
- **Seam signature change.** `create_agent_def(name, system_prompt, allowed_tools, skills_dir, mcp_server_ids, model_overrides, memory_namespace)` and `update_agent_def(name, system_prompt, allowed_tools, skills_dir, mcp_server_ids, model_overrides, memory_namespace)` — the update seam's four new params accept the `_UNSET` sentinel (or a sentinel-equivalent) so omitted PATCH fields pass through. To avoid leaking the store's `_UNSET` into the API layer, the console seam uses `None` as "unchanged" and the server.py wrapper translates `None`→`_UNSET` when calling `create_version`. system_prompt/allowed_tools keep their existing `None`-means-unchanged behavior.
- **Clone passthrough.** Clone (`POST /admin/agents/{name}/clone`) reads the source def and re-creates; it SHALL copy the four fields too so a clone is faithful. Already reads `src["system_prompt"]`/`src["allowed_tools"]` from `_def_response`; extend to the four new fields.
- **_def_response.** Extend to include the four fields from the active version so GET/clone/read paths all carry them.
- **admin.html.** Add four inputs to `#ag-modal`: `#ag-skills-dir` (text), `#ag-mcp-server-ids` (comma/JSON text → array), `#ag-model-overrides` (JSON textarea), `#ag-memory-namespace` (text). `agEdit` prefills from GET; `agSave` serializes. Parse failures (bad JSON) surface an inline error, no submit.

## Risks / Trade-offs

- **JSON inputs in the modal** (`mcp_server_ids`, `model_overrides`) risk malformed input. Mitigate with client-side parse + inline error before POST/PATCH; server still validates via Pydantic.
- **Seam signature widening** touches server.py wiring wrappers (typed inner functions for mypy). Low risk; mirrors the pattern established in the prior CRUD change.
- **`None` vs `{}` ambiguity for `model_overrides`** on PATCH: chose `None`=unchanged. An admin wanting to clear overrides sets `{}` explicitly. Documented in the modal hint.

## Future work (out of scope, needs migration + runtime wiring)

hermes `cli-config.yaml` knobs with no fleetent runtime consumer today: `agent.max_turns`, `agent.reasoning_effort`, `agent.personalities`, `memory.*` toggles/char-limits/nudge intervals, `session_reset.*`, `delegation.*` (max_iterations/max_concurrent_children/max_spawn_depth/orchestrator), `code_execution.*` (timeout/max_tool_calls), `platform_toolsets`. Each needs (1) a new `agent_versions` column via Alembic, (2) wiring into `agent_loop`/`sub_agent`/`sandbox_client`, before it is worth exposing in CRUD.
