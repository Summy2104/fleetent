## Context

Slack connects per **owner**: `ConnectorManager` (keyed by `(owner_id, platform)`)
starts one `slack_adapter.run(owner_id, config)` Socket Mode connection per owner from
`im_connectors` DB rows; `im_connector_config.resolve` reads DB config then `.env`. One
Slack app receives all channels' events; `normalizer.route` resolves the agent
downstream via `get_agent_for_context` (now file-driven).

The just-landed file-driven agent model (`agent_config`: `AgentFile` + `AgentConfigIndex`
+ `scan`/`current`) makes each agent a self-contained `agent.yaml`. This change extends
that atom to own its Slack ingress: each agent declares its own Slack app and runs its
own connection.

Constraints (CLAUDE.md): secrets never inline in config (env-ref only; reuse
`config_validation._looks_inline_secret`); injectable path/state for tests; no ORM;
TDD; adapters/Slack mocked in tests.

## Goals / Non-Goals

**Goals:**
- `agent.yaml connectors.slack` (env-ref tokens + optional channel filter), validated
  and secret-scanned by `agent_config`.
- One Socket Mode connection per declaring agent, supervised by agent name, sourced
  from the agent index; start on boot, reload on re-scan (diff running vs declared).
- Implicit routing: the receiving connection identifies the agent; route skips
  `get_agent_for_context` for Slack.
- Remove owner-level Slack (manager factory, `start_all_enabled`, `/admin/im` Slack
  endpoints, `.env` Slack path, `seed_from_env` Slack).

**Non-Goals:**
- Per-agent channel allowlist / user approval (separate change `per-agent-im-access`).
- Telegram per-agent migration (stays owner-level).
- A DB→file export step for connectors (agent.yaml is authored directly here).

## Decisions

### D1: `connectors.slack` lives in agent.yaml, tokens by env ref
`AgentFile` gains `connectors: {slack: {bot_token_env, app_token_env, channels: []}}`.
Only env-var *names* appear in the file; `agent_config` secret-scan extends over the
`connectors` subtree and fails fast on inline plaintext. Mirrors the inline-MCP +
env-ref decision from file-driven-agent-config. Alternative (DB connector keyed by
agent) rejected: not self-contained, conflicts with the env-ref decision.

### D2: New per-agent connector supervisor, keyed by agent name
A dedicated supervisor (not the owner-level `ConnectorManager`) keyed by `agent_name`,
whose source of truth is `agent_config.current()`. `start_from_index()` starts a
connection for each agent whose `connectors.slack` env tokens resolve; `reload()` diffs
the running set against the declared set and adds/removes; `stop_all()` on shutdown.
Reusing `ConnectorManager` (rekey `owner_id`→`agent`) is rejected — it resolves config
from DB and must still serve owner-level Telegram, so a separate supervisor keeps both
models clean.

### D3: Implicit agent routing for Slack
`slack.create_app(agent_name, cfg)` binds the agent into the `message` handler;
`handle_message` resolves the agent's snapshot from the index by that name and stamps it
onto `NormalizedMessage`. `normalizer.route` uses a pre-resolved agent when present and
skips `get_agent_for_context`; Telegram (no pre-resolved agent) keeps the existing
lookup. A non-empty `connectors.slack.channels` drops events from other channels.

### D4: Reload entry doubles as agent hot-reload
The supervisor's `reload()` re-scans `agent_config` and reconciles connections — filling
the "no agent hot-reload" gap noted in file-driven-agent-config (skills have it, agents
didn't). Exposed for an admin trigger (endpoint wiring can follow).

### D5: Owner-level Slack removed (breaking)
Drop `"slack"` from `ConnectorManager.factories`; `start_all_enabled` no longer starts
Slack; `/admin/im` Slack connector CRUD/enable endpoints removed (or 410);
`im_connector_config` Slack `.env` mapping + `seed_from_env` Slack dropped. The
`im_connectors` table keeps Telegram rows; existing Slack rows become inert.

## Risks / Trade-offs

- **Many Slack apps to provision** (one per agent) → operational cost; documented in the
  schema example; acceptable given the isolation goal.
- **A bad/declaring agent with unresolved env tokens** → its connection is reported
  `unconfigured`/`error` and skipped; the supervisor never crashes other agents.
- **Two channel concepts** (`bindings.channels` for routing vs `connectors.slack.channels`
  for the app's response filter) → documented distinct; routing is implicit for Slack so
  `bindings.channels` is not consulted on the Slack path (avoids confusion).
- **Breaking owner-level Slack** → mitigated by Telegram staying owner-level and clear
  migration notes; rollback = revert this change (Slack rows in DB are untouched).

## Migration Plan

1. Add `connectors.slack` to `AgentFile` + secret scan (no behavior change yet).
2. Make `slack.create_app/run` agent-keyed and stamp the agent on the message.
3. Add the per-agent supervisor; wire it into `server.py` lifespan after
   `agent_config.scan()`.
4. Route on the pre-resolved agent for Slack.
5. Remove owner-level Slack (factory, `start_all_enabled`, admin endpoints, `.env`
   mapping, `seed_from_env`).
   Rollback = revert; Telegram and the `im_connectors` table are unaffected.

## Open Questions

- Where per-agent connection status lives (in-memory in the supervisor vs a small store)
  — default to in-memory + structured logs; a status store can follow if health UI needs
  it.
