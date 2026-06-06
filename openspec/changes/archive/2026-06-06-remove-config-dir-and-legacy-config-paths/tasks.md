## 1. Repository template contract

- [x] 1.1 Write failing tests: repository has only `.env.example`, `platform.yaml.example`,
  `agents/default/agent.yaml.example`, and `agents/default/.env.example` as canonical config
  templates; `config/` does not exist.
- [x] 1.1a Write failing tests: the four canonical examples are complete:
  `agent.yaml.example` covers all `AgentFile` fields; `agents/default/.env.example` covers every env
  reference in `agent.yaml.example`; `.env.example` covers every env reference in
  `platform.yaml.example`; `platform.yaml.example` validates against the Platform / embedded Knowledge
  config loaders.
- [x] 1.2 Implement: remove `config/` and extra `agents/default/*example` files not mapped to a
  runtime file, and fold any missing fields / env keys into the four canonical examples.
- [x] 1.3 Verify docs/tests no longer refer to noncanonical Agent examples and no supported config field
  exists only in deleted examples.

## 2. Runtime and deploy path contract

- [x] 2.1 Write failing tests: `agent run/init/restart`, materialize, admin deploy, and install all
  use `FLEETENT_HOME/agents/<id>/`.
- [x] 2.2 Implement: update path helpers and any direct `paths.base_dir() / name` writes to use
  `agents/<id>/`.
- [x] 2.3 Remove default/root single-file fallback semantics for `FLEETENT_HOME/agent.yaml`.

## 3. Platform and Agent env loading

- [x] 3.1 Write failing tests: Platform `Settings` reads `$FLEETENT_HOME/.env` regardless of cwd,
  external env overrides dotenv, and Agent runtime reads only `<agent-home>/.env`.
- [x] 3.2 Implement home-scoped Platform dotenv loading.
- [x] 3.3 Verify Platform env placeholders do not include Agent runtime secret names.

## 4. MCP file removal

- [x] 4.1 Write failing tests: default startup/global MCP registration does not read
  `config/mcp.servers.yaml`; repo/docs/specs do not present it as current config.
- [x] 4.2 Implement: remove default `MCP_SERVERS_YAML_PATH` behavior; source global and agent MCP
  definitions from Platform DB / materialized `agent.yaml`.
- [x] 4.3 Keep only explicit-path parser helpers if still useful for tests, with no default legacy path.

## 5. OpenSpec/docs guardrails

- [x] 5.1 Write guard tests scanning active docs/specs for forbidden current-path strings:
  `config/settings.yaml`, `config/mcp.servers.yaml`, `config/agent/`, `config/platform/`,
  `config/agents/`, `FLEETENT_HOME/agent.yaml`, and `FLEETENT_HOME/<id>/agent.yaml`.
- [x] 5.2 Update OpenSpec capabilities: `configuration`, `runtime-paths`, `agent-runtime-cli`,
  `platform-agent-lifecycle`, and `mcp-client`.
- [x] 5.3 Update README and deployment docs.

## 6. Quality gates

- [x] 6.1 Run `openspec validate remove-config-dir-and-legacy-config-paths --strict`.
- [x] 6.2 Run `openspec validate --specs --strict`.
- [x] 6.3 Run targeted tests for config paths, install, agent runtime CLI, materialize, admin deploy,
  MCP runtime, and deployment docs.
- [x] 6.4 Run `uv run ruff check src tests`.
