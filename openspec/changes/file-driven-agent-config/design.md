## Context

Runtime agent resolution lives in `runtime/snapshot.py`. Today it reads
`agents`/`agent_versions` (definition + active version), `channel_agents`/`user_agents`
(routing), and `agent_mcp_server_store` (per-agent MCP) out of SQLite, producing the
immutable `AgentSnapshot` that `runtime/loop.py` consumes. The IM normalizer calls
`resolve_agent_for_request(platform, channel, user)`; tool filtering uses the pure
`filter_tool_schemas`. Trace logging is already file-based (`data/traces.jsonl`).

We want an agent to be a portable atom: one self-contained
`config/agents/<name>/agent.yaml` that fully describes it, loaded at runtime with zero
DB access. The Web admin console + DB stay the **authoring** source of truth; a
separate (out-of-scope) export step generates `agent.yaml` from DB rows, stamping a
`version` that corresponds to the DB version. This change defines the **file schema
contract** and the **zero-DB runtime loader** that consumes it.

Constraints (from CLAUDE.md): no ORM, secrets never in config files (precedent:
`SecretRejectingYamlSettingsSource`), named-parameter SQL only, injectable path
constants for test isolation, mypy strict, TDD hard gate.

## Goals / Non-Goals

**Goals:**
- A self-contained per-agent file format that maps 1:1 onto the data needed to build
  an `AgentSnapshot` plus channel/user bindings.
- A loader + in-memory index that resolves agents and routing from files only, with
  the runtime path provably touching no database.
- Preserve `runtime/snapshot.py`'s public API and `AgentSnapshot` shape so downstream
  (`runtime/loop.py`, normalizer, tool filtering) is unchanged.
- Reject inline plaintext secrets at scan time.

**Non-Goals:**
- The DB→file export/generation step (separate owner).
- Web admin console changes; DB remains authoring source of truth.
- Historical-version resolution and version pinning (`load_version`,
  `load_version_by_name` for non-active versions) — stay DB/authoring side.
- Full connector-store and stats `agent_id`→name schema rekey (deferred follow-up).

## Decisions

### D1: Directory-per-agent with fixed `agent.yaml`
`config/agents/<name>/agent.yaml`; identity = directory name, validated to equal the
in-file `name`. Mirrors the `skills/<name>/SKILL.md` convention. Alternative (flat
`config/agents/<name>.yaml`) rejected to leave room for future per-agent sidecar
assets (prompt includes, fixtures) without changing the layout. Single global
`config/agents.yaml` rejected: breaks the "copy one unit to move one agent" atom goal.

### D2: New module `fleetent/agent_config.py`
Holds the pydantic file model(s), the injectable `AGENTS_DIR` constant (overridable by
`FLEETENT_AGENTS_DIR`), `scan()` → `AgentConfigIndex`, and the lookups the snapshot
layer needs. Structure per CLAUDE.md: imports → constants → dataclasses/models →
functions. Reuses `config.McpServerSettings` for inline MCP entries.

### D3: Scan timing mirrors skills
Server scans once at FastAPI lifespan startup (like `skill_registry.scan()`); CLI
`run()` scans per invocation. The index is the single in-memory source for both
definition lookup and routing.

### D4: `snapshot.py` rewired, API/shape preserved (route A + inline MCP)
`load_active(name)` and `resolve_agent_for_request(...)` read the index instead of
`agent_store`. `AgentSnapshot` keeps its fields; `resolve_mcp_servers` overlays the
file's inline `mcp_servers` onto global defaults with no DB call. `filter_tool_schemas`
is untouched. Alternative (new `AgentDefinition` model + reshaped snapshot, "pure B")
rejected as a larger blast radius for no runtime behavior gain.

### D5: Runtime identity = agent name (string)
`AgentSnapshot`'s identity field changes from `agent_id: int` to a string holding the
agent `name`; `connector_scope` returns that string. This is the one `AgentSnapshot`
shape change. The connector-store/stats DB tables remain keyed by int `agent_id`; their
rekey to string keys is a separate follow-up. OAuth-connector resolution (secrets in
DB) is not on the zero-DB runtime path, so the connector-store call site is adapted to
the string identity (or short-circuited on the file path) here without the full rekey.

### D6: Inline MCP, secrets by env reference
`mcp_servers` are full inline definitions (reusing `McpServerSettings`); real secrets
appear only as `api_key_env`/`credential_ref` env-var names. `scan()` runs the existing
secret-detection (`config_validation._looks_inline_secret`) over each file and rejects
inline plaintext, consistent with `SecretRejectingYamlSettingsSource`.

### D7: Routing index + conflict detection
`scan()` builds `name→def`, `(platform,channel)→name`, `user→name`, and the set of
`default` agents. Two agents claiming the same channel, the same user, or more than one
`default` is a hard scan error (fail fast). Resolution precedence is unchanged:
channel > user > default > bare run.

## Risks / Trade-offs

- **Dual source of truth drift** (DB authoring vs file runtime) → the `version` field
  ties a file to its DB version for traceability; export is the reconciliation owner.
- **Identity ripple** (`agent_id`→name) touching connectors/stats → scoped out and
  documented; `connector_scope` returns name; full rekey is a follow-up.
- **Scan-time failure surface** (a malformed file breaks startup) → fail fast with the
  offending file + field named, matching `config.py`'s error style; bad files never
  load silently.
- **Loss of runtime version pinning** (channel `bound_version_id`) → runtime already
  only serves the active version (`resolve_agent_for_request` ignores
  `bound_version_id` today), so no behavioral regression.

## Migration Plan

1. Land `agent_config.py` (schema + loader + index) behind tests; no wiring yet.
2. Rewire `snapshot.py` `load_active`/`resolve_agent_for_request`/`resolve_mcp_servers`
   to the index; keep version-specific loaders DB-backed (authoring).
3. Wire `scan()` into FastAPI lifespan and CLI `run()`.
4. Rollback = revert the `snapshot.py` rewire; the DB read path is untouched and can be
   restored, since this change does not delete the authoring tables.

## Open Questions

- Final home of `agent_config.py` (top-level vs a package) — defer to implementation,
  following the established package-architecture boundaries.
