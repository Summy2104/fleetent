## Why

Slack connects at the **owner** level: one shared Slack app per owner receives all
channels' events, and a downstream lookup routes each message to an agent. That makes
the Slack connection shared infrastructure that no single agent owns — at odds with the
"agent is a self-contained atom" model just established for agent definitions. We want
each agent to bring its own Slack app: its own bot identity, its own credentials and
scopes, isolated from other agents, and declared in its own `agent.yaml`.

## What Changes

- **agent.yaml gains a `connectors.slack` block** (`bot_token_env`, `app_token_env`,
  optional `channels` filter). Tokens are referenced by env-var name only; the scanner
  rejects inline plaintext (reusing the existing secret-detection), extended to the
  `connectors` subtree.
- **Each declaring agent runs its own Socket Mode connection.** A new per-agent
  connector supervisor (keyed by agent name, sourced from the `agent_config` index)
  starts one connection per agent whose `connectors.slack` env tokens resolve, on
  startup and on agent re-scan; it diffs running vs declared to add/remove connections.
  This also adds the agent hot-reload entry the file-driven model was missing.
- **Routing becomes implicit:** the connection that receives an event already
  identifies the agent. `slack.create_app(agent_name, …)` binds the agent into the
  handler; the message carries the resolved agent, so `normalizer.route` skips
  `get_agent_for_context` for Slack. A non-empty `connectors.slack.channels` filters
  which channels the app responds in.
- **BREAKING — owner-level Slack is removed:** Slack is dropped from the owner-level
  `ConnectorManager` factories and `start_all_enabled`; the `/admin/im` Slack connector
  endpoints are removed; `.env SLACK_BOT_TOKEN`/`SLACK_APP_TOKEN` are no longer the
  Slack path (per-agent env names replace them); `seed_from_env` drops Slack. Telegram
  stays owner-level, unchanged.

Out of scope (separate change `per-agent-im-access`): making the channel allowlist and
user approval per-agent — this change keeps them as-is (owner/shared). Telegram
per-agent migration is also out of scope.

## Capabilities

### New Capabilities
- `per-agent-slack-connector`: the `agent.yaml connectors.slack` schema, the per-agent
  Socket Mode supervisor (start/stop/reload keyed by agent, sourced from the agent
  index), per-agent connection status, and implicit agent routing for Slack.

### Modified Capabilities
- `file-agent-runtime`: `agent.yaml` gains an optional `connectors.slack` block;
  secret rejection extends to the `connectors` subtree.
- `im-connector-config`: Slack credentials are no longer resolved from the owner-level
  DB connector / `.env`; they come from each agent's `connectors.slack` env references.
- `im-connector-registry`: Slack connectors are no longer owner-keyed rows started by
  `start_all_enabled`; they are per-agent connections supervised from the agent index.
- `im-gateway`: Slack message routing resolves the agent implicitly from the receiving
  connection rather than via `get_agent_for_context` channel resolution.

## Impact

- **Code**: `agent_config` (`AgentFile.connectors.slack` model + index query + secret
  scan); `im_gateway/slack.py` (`create_app`/`run` keyed by agent name, message stamps
  agent); new per-agent connector supervisor; `im_gateway/normalizer.py` (route accepts
  a pre-resolved agent for Slack); `server.py` lifespan (start per-agent Slack from the
  index; remove owner-level Slack); `im_connector_config`/`im_admin_api` (drop Slack
  owner path + endpoints).
- **Config/ops**: per-agent Slack apps and env vars replace the single owner Slack app;
  each agent that wants Slack declares `connectors.slack`.
- **No new dependencies** (reuses `slack-bolt`, `pyyaml`, existing secret-detection).
- **Tests**: new unit + integration suites; owner-level Slack removal asserted; adapters
  and Slack fully mocked.
