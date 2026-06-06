## Decisions

### D1. No `config/` Namespace

The repository and runtime SHALL stop using `config/` as a current config namespace. This includes
templates, runtime config, Knowledge config, MCP config, and examples.

Reasoning: Keeping an empty-but-meaningful `config/` namespace creates an attractive nuisance.
Future contributors will keep adding module-level files there because old specs and code mention it.
MVP can remove it without migration debt.

### D2. One Canonical Template Per Runtime File

Each runtime file has at most one adjacent `.example`:

- Platform `.env` -> `.env.example`
- Platform `platform.yaml` -> `platform.yaml.example`
- Agent `agent.yaml` -> `agents/default/agent.yaml.example`
- Agent `.env` -> `agents/default/.env.example`

Additional examples such as `.env.standalone.example`, `agent.configure.yaml.example`, and
`agent.defaults.yaml.example` are removed. Their useful explanatory content should move into docs or
the canonical template comments.

The four remaining examples are not minimal skeletons. They are complete reference examples:

- `platform.yaml.example` includes every currently supported Platform non-secret config section and
  every embedded Platform capability config section that is file-authored in the MVP.
- `.env.example` includes every Platform process env key and every env key referenced by
  `platform.yaml.example`.
- `agents/default/agent.yaml.example` includes every current `AgentFile` field, including runtime
  governance, intelligence, deployment/process, access, connectors, bindings, MCP, model targets, and
  routes.
- `agents/default/.env.example` includes every env key referenced by
  `agents/default/agent.yaml.example`.

Completeness should be tested against schemas / parsed example references where possible, not maintained
only by manual review.

### D3. Agent Home Under `agents/<id>/`

All agent runtime and deployment paths resolve to `FLEETENT_HOME/agents/<agent-id>/`.

This applies to:

- `fleetent agent run <id>`
- `fleetent agent init <id>`
- `fleetent agent restart <id>`
- Platform materialize
- Admin deploy/export write path
- install default agent seed

`--home PATH` remains an explicit override for standalone CLI commands, but default resolution never
uses `FLEETENT_HOME/<id>/` or `FLEETENT_HOME/agent.yaml`.

### D4. Platform Env Is Home-Scoped

Platform settings SHALL load `$FLEETENT_HOME/.env` as the platform dotenv file, with external process
env taking precedence. Agent runtime already loads `<agent-home>/.env` with `override=False`; the
Platform side should mirror that home-scoped behavior rather than relying on current working
directory.

### D5. MCP Is DB/Authored, Not File-Authored

MCP server definitions SHALL be authored in Platform DB. Global-default servers use `agent_id IS NULL`;
agent-owned servers use an agent id. Materialize writes an agent's effective MCP bindings into that
Agent's `agent.yaml`.

The default startup path SHALL NOT read `config/mcp.servers.yaml`. If a test or utility needs to parse
MCP YAML, it must pass an explicit path to a helper; there is no default legacy path.

### D6. Guard Tests Are Part Of The Contract

This change should add tests that fail when old paths appear in active docs/specs or when repository
templates are reintroduced under `config/`. These tests are intentional process guardrails so future
parallel work follows the same contract.

## Impacted Modules

- `src/fleetent/paths.py`
- `src/fleetent/config.py`
- `src/fleetent/__main__.py`
- `src/fleetent/runtime/agent_app.py`
- `src/fleetent/runtime/agent_init.py`
- `src/fleetent/agent_config.py`
- `src/fleetent/platform/admin_cli/init_config.py`
- `src/fleetent/platform/agent_lifecycle/materialize.py`
- `src/fleetent/platform/agent_management_console/agent_admin_api.py`
- `src/fleetent/platform/connector_management/*mcp*`
- `scripts/install.sh`
- `Dockerfile` / `docker-compose.yml`
- README, deployment docs, OpenSpec specs

## Risks

- Existing local checkouts using old `config/` paths will break. This is acceptable for MVP.
- Removing extra Agent examples reduces inline operator guidance. Mitigate by keeping the single
  `agents/default/agent.yaml.example` comprehensive and moving long explanations to docs.
- MCP file removal may affect tests that still construct `config/mcp.servers.yaml`; update those tests to use
  DB authoring or explicit parser helpers.
