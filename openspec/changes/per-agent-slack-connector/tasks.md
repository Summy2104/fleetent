## 1. agent.yaml connectors.slack schema

- [x] 1.1 Write failing unit tests: `AgentFile` parses `connectors.slack`
  (`bot_token_env`/`app_token_env`/optional `channels`); `connectors` absent is valid;
  inline token-like value under `connectors` is rejected by the secret scan (file+field
  named); env-name references accepted.
- [x] 1.2 Add `connectors`/`SlackConnector` models to `AgentFile` and extend the secret
  scan to the `connectors` subtree. Make 1.1 green.
- [x] 1.3 Write failing unit test: the index exposes the agents that declare a Slack
  connector (e.g. `AgentConfigIndex.slack_agents()`); 1.4 implement it green.

## 2. Slack adapter keyed by agent

- [x] 2.1 Write failing unit tests: `slack.create_app(agent_name, cfg)` builds an app
  bound to `agent_name`; `handle_message` stamps the resolved agent onto the
  `NormalizedMessage`; a non-empty `channels` filter drops events from other channels.
- [x] 2.2 Rework `slack.create_app`/`run` to be agent-keyed (signature `agent_name`,
  config carries `bot_token`/`app_token`/`channels`), stamp the agent, apply the channel
  filter. Make 2.1 green.

## 3. Implicit Slack routing

- [x] 3.1 Write failing unit tests: `normalizer.route` uses a pre-resolved agent stamped
  on the message (skips `get_agent_for_context`); Telegram path (no stamped agent) still
  resolves via the index as before.
- [x] 3.2 Add a pre-resolved-agent field to `NormalizedMessage` and branch `route` to use
  it for Slack. Make 3.1 green.

## 4. Per-agent connector supervisor

- [x] 4.1 Write failing unit tests (mock adapter `run`): supervisor starts one connection
  per agent declaring Slack with resolvable env tokens; an agent with a missing env token
  is reported unconfigured/error and skipped without affecting others; `stop`/`reload`
  add/remove connections by diffing running vs declared.
- [x] 4.2 Implement the per-agent connector supervisor (keyed by agent name, sourced from
  `agent_config.current()`; resolves env tokens; per-agent status). Make 4.1 green.

## 5. Wiring + remove owner-level Slack

- [x] 5.1 Write failing integration tests: server lifespan starts per-agent Slack from the
  index after `agent_config.scan()`; `start_all_enabled` and the owner `ConnectorManager`
  no longer start Slack; `/admin/im` Slack connector endpoints are gone; Telegram still
  starts owner-level.
- [x] 5.2 Wire the supervisor into `server.py` lifespan; drop `"slack"` from
  `ConnectorManager.factories`/`start_all_enabled`; remove `/admin/im` Slack endpoints;
  drop Slack from `im_connector_config` schema/`.env` mapping/`seed_from_env`. Make 5.1
  green.

## 6. Closeout

- [x] 6.1 Update the `agent.yaml.example` to show `connectors.slack` (env-ref tokens).
- [x] 6.2 Migrate any existing Slack/connector tests broken by the owner-level removal to
  the per-agent model.
- [x] 6.3 `uv run ruff format src tests && uv run ruff check src tests` and
  `uv run mypy src` (no new errors over baseline).
- [x] 6.4 Full suite `uv run pytest -x -q` green.
