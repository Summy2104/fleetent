# agent-resource-isolation Specification

## Purpose
TBD - created by archiving change 2026-05-29-multi-agent-management. Update Purpose after archive.
## Requirements
### Requirement: Per-agent skills directory
An `AgentSnapshot` MAY specify `skills_dir`. When set, the agent loop SHALL use an isolated `SkillIndex` rooted at that directory to match and load skills, ignoring the global skill index for that request. When unset, the global `skill_registry` SHALL be used.

#### Scenario: Custom skills_dir wins
- **WHEN** an agent's snapshot has `skills_dir="agents/analyst/skills"` and that directory contains a `weekly-report` skill
- **AND** an incoming message triggers `weekly-report`
- **THEN** the `weekly-report` SKILL.md from `agents/analyst/skills` is injected into the system prompt

#### Scenario: Falls back to global when null
- **WHEN** an agent's snapshot has `skills_dir=None`
- **THEN** the global `skill_registry` index is consulted as before

#### Scenario: SkillIndex test isolation
- **WHEN** tests pass a `tmp_path` as `skills_dir`
- **THEN** `SkillIndex` operates only on that directory and does not mutate the global module-level index

### Requirement: Per-agent MCP server allowlist
An `AgentSnapshot.mcp_server_ids` SHALL constrain which MCP server tools are visible to the agent. MCP tools whose `{server_id}__` prefix is not in the list SHALL be filtered out of the tool schema for that request.

#### Scenario: Tool from allowed server visible
- **WHEN** `mcp_server_ids = ["github"]` and the request happens to invoke `github__create_issue`
- **THEN** the tool schema offered to the LLM contains `github__create_issue`

#### Scenario: Tool from non-allowed server hidden
- **WHEN** `mcp_server_ids = ["github"]` and `gitlab__create_issue` is also registered
- **THEN** the tool schema offered to the LLM does NOT contain `gitlab__create_issue`

#### Scenario: Empty list hides all MCP tools
- **WHEN** `mcp_server_ids = []`
- **THEN** no MCP server tool appears in the schema; built-in tools are unaffected

### Requirement: Per-agent model overrides
An `AgentSnapshot.model_overrides` MAY override fields of `ROUTES[task_type]` for the duration of a request. Supported overrides per task type SHALL include at least `base_url`, `model`, `api_key_env`, `max_tokens`, and `fallbacks`.

#### Scenario: Override default model
- **WHEN** `model_overrides = {"default": {"model": "gpt-4o-mini"}}`
- **THEN** `get_async_client_and_config("default", overrides=snapshot.model_overrides)` returns a route config where `model == "gpt-4o-mini"` and other fields match the global `ROUTES["default"]`

#### Scenario: Override memory extraction route only
- **WHEN** `model_overrides = {"memory_extraction": {"model": "local-haiku"}}`
- **THEN** memory extraction uses `local-haiku` but the default route is unchanged

#### Scenario: No override for unknown task_type
- **WHEN** the snapshot's overrides dict has no entry for the requested `task_type`
- **THEN** the global `ROUTES[task_type]` is used as-is

### Requirement: Per-agent memory namespace
Per-user semantic memory is stored in the `memory_items` SQLite table. That table SHALL carry a `namespace` column (NOT NULL, default `"default"`), and all memory reads and writes SHALL be scoped by `(user_id, namespace)`. `AgentSnapshot.memory_namespace` SHALL drive which namespace a request uses. The public API `extract_and_update(user_id, conversation, namespace="default")` and `search(user_id, query, namespace="default")` SHALL accept and honor the namespace. The corresponding vector index SHALL be keyed by namespace via `vector_store.memory_namespace(user_id, namespace="default")`, which SHALL return `mem:{user_id}` for the default namespace (preserving existing vectors) and `mem:{user_id}:{namespace}` otherwise.

#### Scenario: Namespaced store/load
- **WHEN** an agent runs with `memory_namespace="analyst"` for user `u1` and a fact is extracted
- **THEN** the row is written with `namespace="analyst"`
- **AND** a `memory_snapshot(user_id="u1", namespace="analyst")` returns only facts in that namespace

#### Scenario: Different namespaces isolate
- **WHEN** user `u1` has memories under namespace `analyst` and separately under `cs`
- **THEN** reads scoped to `cs` do not include facts written under `analyst`

#### Scenario: Backwards-compatible default
- **WHEN** no namespace is specified anywhere
- **THEN** the default namespace `"default"` is used, and `vector_store.memory_namespace("u1")` returns `mem:u1` unchanged

### Requirement: Memory namespace schema migration
An Alembic migration SHALL add the `namespace` column to `memory_items` with server default `"default"` so existing rows are backfilled to the default namespace. `downgrade` SHALL drop the column. No filesystem data-move script is required, because memory is stored in SQLite, not per-user JSONL files.

#### Scenario: Existing rows backfilled
- **WHEN** the migration upgrades a database containing pre-existing `memory_items` rows
- **THEN** every existing row has `namespace = "default"`

#### Scenario: Downgrade drops column
- **WHEN** the migration is downgraded
- **THEN** the `namespace` column no longer exists on `memory_items`

