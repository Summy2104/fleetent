## ADDED Requirements

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
`memory_layer` SHALL store and load memories at `data/users/{user_id}/memories/{namespace}.jsonl`. `AgentSnapshot.memory_namespace` SHALL drive which file is used.

#### Scenario: Namespaced load/save
- **WHEN** an agent runs with `memory_namespace="analyst"` for user `u1`
- **THEN** new memory facts are appended to `data/users/u1/memories/analyst.jsonl`
- **AND** `load_memories(user_id="u1", namespace="analyst")` returns only those facts

#### Scenario: Different namespaces isolate
- **WHEN** user `u1` interacts first with an agent using `memory_namespace="analyst"`, then with one using `memory_namespace="cs"`
- **THEN** the `cs` namespace does not include facts written under `analyst`

#### Scenario: Backwards-compatible default
- **WHEN** no namespace is specified anywhere
- **THEN** the default namespace `"default"` is used and the file is `data/users/{user_id}/memories/default.jsonl`

### Requirement: Migration of pre-namespace memory files
A one-shot migration script SHALL move any pre-existing `data/users/{user_id}/memories.jsonl` to `data/users/{user_id}/memories/default.jsonl`. The script SHALL be idempotent.

#### Scenario: Legacy file migrated
- **WHEN** `scripts/migrate_memories_to_namespace.py` is run with `data/users/u1/memories.jsonl` present
- **THEN** the file is moved to `data/users/u1/memories/default.jsonl` and the old path no longer exists

#### Scenario: Already migrated is a no-op
- **WHEN** the migration script is run a second time
- **THEN** no error occurs and no files are modified

### Requirement: Module path constants remain monkeypatchable
All new module-level path constants introduced by this change SHALL be defined at module top so tests can override them via `monkeypatch.setattr(module, "CONSTANT", tmp_path)`.

#### Scenario: Memory namespace dir override
- **WHEN** a test runs `monkeypatch.setattr(memory_layer, "MEMORIES_ROOT", tmp_path)`
- **THEN** subsequent `load_memories` / `extract_and_save` calls operate under `tmp_path` and do not touch `data/`
