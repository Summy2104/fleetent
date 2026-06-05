# file-agent-runtime Specification

## Purpose
TBD - created by archiving change file-driven-agent-config. Update Purpose after archive.
## Requirements
### Requirement: Self-contained agent config file

The system SHALL load each agent from a self-contained file at
`config/agents/<name>/agent.yaml` (directory per agent, fixed filename). The agents
root directory SHALL be an injectable constant overridable by the `FLEETENT_AGENTS_DIR`
environment variable. The agent's identity SHALL be the directory name, which MUST
equal the in-file `name` field.

The file SHALL fully describe the agent with these fields: `name`, `version`
(integer, corresponds to the authoring DB version), `tenant_id`, `team_id`,
`system_prompt`, `model_overrides`, `memory_namespace`, `skills_dir` (nullable;
null means the global default), `allowed_skills` (empty means no narrowing),
`allowed_tools`, `plugins`, `features` (e.g. `code_execution`, `sandbox_env`), inline
`mcp_servers`, and `bindings` (`default`, `channels`, `users`).

#### Scenario: Valid file resolves to an AgentSnapshot

- **WHEN** `config/agents/support/agent.yaml` exists with `name: support` and a valid schema
- **THEN** loading agent `support` returns an `AgentSnapshot` whose `system_prompt`,
  `allowed_tools`, `skills_dir`, `model_overrides`, and `memory_namespace` come from
  that file, and whose identity is the name `support`

#### Scenario: Directory name must match in-file name

- **WHEN** `config/agents/support/agent.yaml` declares `name: helpdesk`
- **THEN** the scan fails fast with an error naming the file and the mismatch

#### Scenario: FLEETENT_AGENTS_DIR overrides the agents root

- **WHEN** `FLEETENT_AGENTS_DIR` points at a temporary directory containing
  `assistant/agent.yaml`
- **THEN** agent `assistant` is resolved from that directory and `config/agents/` is
  not read

### Requirement: Zero-database runtime resolution

Resolving an agent and its routing at runtime SHALL NOT perform any database access.
The agent definition, bindings, and inline MCP servers SHALL be served entirely from
the in-memory index built by scanning the agents directory.

#### Scenario: Runtime path performs no DB access

- **WHEN** an agent is resolved and run from files while the database layer is rigged
  to raise on any access
- **THEN** resolution and the run proceed without raising, proving no DB call occurred

### Requirement: Scan-built in-memory index

The system SHALL scan the agents directory and build an in-memory index mapping agent
name to definition, `(platform, channel_id)` to agent name, `user_id` to agent name,
and the set of default agents. The server SHALL scan once at startup; the CLI SHALL
scan per invocation.

#### Scenario: Index built from multiple agent files

- **WHEN** the agents directory contains `support/agent.yaml` and `sales/agent.yaml`
- **THEN** the index resolves both names, and each agent's channels and users map back
  to its name

#### Scenario: Empty or missing agents directory yields no agents

- **WHEN** the agents directory is absent or empty
- **THEN** the index is empty and agent lookups return nothing (bare run), with no error

### Requirement: Inline MCP overlay without database

Per-agent MCP servers SHALL be defined inline in the agent file as full server
definitions. Effective MCP resolution SHALL overlay the agent's inline `mcp_servers`
onto the global defaults with no database lookup.

#### Scenario: Inline MCP overlaid on defaults

- **WHEN** an agent file defines an inline `mcp_servers` entry with id `acme`
- **THEN** the effective MCP server set for that agent includes `acme` overlaid on the
  global defaults, resolved without any database access

### Requirement: Secrets rejected in agent files

The scan SHALL reject any agent file containing an inline plaintext secret, anywhere in
the file including the `mcp_servers` and `connectors` subtrees. Secret material SHALL be
referenced only by environment-variable name (e.g. `api_key_env`, `bot_token_env`,
`app_token_env`, `credential_ref`).

#### Scenario: Inline plaintext secret is rejected

- **WHEN** an agent file's `mcp_servers` entry contains an inline token-like value
  instead of an `api_key_env` reference
- **THEN** the scan fails fast with an error identifying the file and field

#### Scenario: Inline secret under connectors is rejected

- **WHEN** an agent file's `connectors.slack.bot_token_env` holds an inline token-like
  value instead of an environment-variable name
- **THEN** the scan fails fast, identifying the agent and field

#### Scenario: Env reference is accepted

- **WHEN** an agent file references secrets only by env-var name (e.g.
  `api_key_env: ACME_MCP_TOKEN`, `bot_token_env: SUPPORT_SLACK_BOT`)
- **THEN** the scan accepts the file

### Requirement: Binding conflicts fail fast

The scan SHALL reject configurations where two agents claim the same channel, the same
user, or where more than one agent declares itself the default.

#### Scenario: Two agents bind the same channel

- **WHEN** `support/agent.yaml` and `sales/agent.yaml` both list channel `slack:C123`
- **THEN** the scan fails fast with an error naming the conflicting channel and agents

#### Scenario: Multiple default agents

- **WHEN** two agent files both set `bindings.default: true`
- **THEN** the scan fails fast with an error naming the conflicting agents

### Requirement: Agent file may declare platform connectors

The agent file model SHALL accept an optional `connectors` block declaring per-agent
platform connections, and SHALL validate it. Per-platform connector semantics are
defined by the relevant connector capability (e.g. `per-agent-slack-connector`). Secret
material under `connectors` MUST be referenced by environment-variable name only.

#### Scenario: connectors block accepted

- **WHEN** an `agent.yaml` includes a `connectors.slack` block with env-reference token names
- **THEN** the agent loads with that connector declaration available to the connector layer

#### Scenario: connectors block optional

- **WHEN** an `agent.yaml` omits `connectors`
- **THEN** the agent loads normally

### Requirement: Single-file agent home loading
当 agent home 根目录存在 `agent.yaml`（`FLEETENT_HOME/agent.yaml`，扁平、无 `config/` 子目录）时，运行时 SHALL 将其作为唯一且默认的 agent 加载，优先于 `config/agents/` 多扫描；该单文件不要求位于 `<name>/` 子目录，因此 SHALL 跳过「目录名等于 name」校验。

#### Scenario: Home-root agent.yaml is loaded as the sole agent
- **WHEN** `FLEETENT_HOME/agent.yaml` 存在且校验通过
- **THEN** 索引只含该一个 agent（`name` 取自文件）
- **AND** 不扫描 `config/agents/`

#### Scenario: Home-root single agent is forced default
- **WHEN** 以单文件模式加载 `FLEETENT_HOME/agent.yaml`，且其 `bindings.default` 为 false 或缺省
- **THEN** 索引的 `default` 等于该 agent 的 `name`
- **AND** 未匹配具体 channel/user 的请求路由到该默认 agent

#### Scenario: Home-root file skips directory-name check
- **WHEN** `FLEETENT_HOME/agent.yaml` 的 `name` 与任何目录名无关（无 `<name>/` 父目录）
- **THEN** 加载成功，不因目录名不匹配而失败
- **AND** 仍执行 inline secret 拒绝校验

#### Scenario: Falls back to multi-scan when home-root file absent
- **WHEN** `FLEETENT_HOME/agent.yaml` 不存在
- **THEN** 运行时回退到既有 `config/agents/` 多扫描
- **AND** 多扫描的 default 仍由 `bindings.default` 决定

#### Scenario: Home-root bindings still populate routing
- **WHEN** 单文件 agent 声明 `bindings.channels` 或 `users`
- **THEN** 这些绑定进入 `by_channel`/`by_user` 路由表
- **AND** 同时该 agent 仍是 default

### Requirement: Agent file may carry intelligence configuration
The agent file model SHALL accept optional typed intelligence configuration blocks so the
deployed agent template can carry non-secret intelligence settings without requiring a
global settings template.

#### Scenario: Agent YAML accepts intelligence config blocks
- **WHEN** an `agent.yaml` declares `vector_store`, `embedding`, `rerank`,
  `knowledge_base`, and `long_term_ctx`
- **THEN** the agent file loads successfully
- **AND** those blocks are available as typed configuration objects on the loaded agent

#### Scenario: Intelligence config uses env references for secrets
- **WHEN** an `agent.yaml` declares real provider or connector configuration
- **THEN** API keys, OAuth credentials, and connector tokens are expressed as env-var
  reference field names
- **AND** no secret payload is required in the agent file

#### Scenario: Existing agent files remain valid
- **WHEN** an `agent.yaml` omits intelligence configuration blocks
- **THEN** the agent file loads with conservative typed defaults
- **AND** runtime behavior remains unchanged

### Requirement: Per-agent runtime governance config

The self-contained `agent.yaml` SHALL additionally accept a per-agent runtime
governance configuration covering: context compression (`context_max_tokens`,
`context_compress_threshold`, `context_keep_recent`, `context_tmax_ratio`,
`context_tretained_ratio`, `compression_initial_intent_max`, `context_flap_window`,
`context_min_savings_ratio`, `context_min_interval_turns`); layered budget on the
`session_*` / `user_*` / `agent_*` dimensions (`agent_budget_session_turns`,
`agent_budget_session_tokens`, `agent_budget_user_turns`, `agent_budget_user_tokens`,
`agent_budget_agent_turns`, `agent_budget_agent_tokens`, `agent_budget_user_window`,
`agent_budget_agent_window`); loop/budget/guardrail controls (`agent_max_turns`,
`agent_max_consecutive_failures`, `agent_max_tokens`, `agent_grace_call_token_ratio`,
`agent_grace_call_min_tokens`, `agent_loop_repeat_threshold`, `guardrail_repeat_threshold`,
`agent_tool_parallel_max`, `loop_detect_ignore_arg_keys`, `sub_agent_timeout_seconds`,
`tool_default_timeout_seconds`); permission gate timeouts
(`permission_gate_medium_timeout_seconds`, `permission_gate_high_timeout_seconds`); and
provider circuit breaker (`provider_failure_threshold`, `provider_cooldown_seconds`).

Each field SHALL be optional, and its default SHALL equal the corresponding current
`Settings` default so that an `agent.yaml` omitting all governance fields is equivalent
to today's global defaults. These fields are per-agent: two agents MAY carry different
governance values without interfering. This requirement adds schema acceptance only;
runtime wiring (reading these from agent config instead of `Settings`) is out of scope
for this change.

#### Scenario: agent.yaml with governance fields parses

- **WHEN** an `agent.yaml` declares `agent_max_turns: 30` and `context_compress_threshold: 0.7`
- **THEN** loading the agent succeeds and the parsed agent carries `agent_max_turns == 30`
  and `context_compress_threshold == 0.7`

#### Scenario: Omitted governance fields fall back to current defaults

- **WHEN** an `agent.yaml` declares no governance fields
- **THEN** the parsed agent's governance values equal the corresponding `Settings` defaults
  (e.g. `agent_max_turns == 50`, `tool_default_timeout_seconds == 30.0`)

#### Scenario: Two agents carry independent governance values

- **WHEN** agent `a` declares `agent_max_turns: 30` and agent `b` declares `agent_max_turns: 80`
- **THEN** each parsed agent carries its own value, proving the field is per-agent

### Requirement: Per-agent deployment and process config

The self-contained `agent.yaml` SHALL additionally accept per-agent deployment/process
configuration: `microsandbox_url`; logging (`log_format`, `observability.logging`
console/file levels, directory, json toggle); `diagnostics` (export dir + retention);
session disk management (`session_ttl_days`, `session_max_total_mb`, `session_max_count`,
`session_cleanup_interval_seconds`); self-hosted image/vision endpoints (`image_gen_url`,
`image_gen_model`, `vision_url`, `vision_model`); `disabled_skills`; and the `mcp`,
`scheduling`, `webhooks` toggles. Existing `config.py` sub-models (`ObservabilitySettings`,
`DiagnosticsSettings`, `McpSettings`, `SchedulingSettings`, `WebhooksSettings`) SHALL be
reused as the nested structures rather than redefined. Defaults SHALL equal current
`Settings` defaults. This requirement adds schema acceptance only; runtime wiring is out
of scope for this change.

#### Scenario: agent.yaml with deployment fields parses

- **WHEN** an `agent.yaml` declares `microsandbox_url: "http://sandbox:7777"` and
  `session_ttl_days: 7`
- **THEN** loading the agent succeeds and the parsed agent carries those values

#### Scenario: Nested observability block reuses existing sub-model

- **WHEN** an `agent.yaml` declares `observability.logging.console_level: debug`
- **THEN** the parsed agent's observability block is an `ObservabilitySettings` with
  `logging.console_level == "debug"`

### Requirement: Global budget and database_url excluded from agent.yaml

The self-contained `agent.yaml` SHALL NOT accept the global (cross-agent) budget
dimension `agent_budget_global_turns`, `agent_budget_global_tokens`, or
`agent_budget_global_window`: in the distributed per-agent-process model there is no
runtime that aggregates a cross-agent total, so this dimension is dropped from the
consolidated config. The `agent.yaml` SHALL also NOT accept `database_url`; the database
location is derived from the agent home (`<home>/data/fleetent.db`) and never written as
an absolute path in the file.

#### Scenario: global budget field is rejected

- **WHEN** an `agent.yaml` declares `agent_budget_global_tokens: 1000`
- **THEN** loading fails fast with a schema error naming the unknown field

#### Scenario: database_url field is rejected

- **WHEN** an `agent.yaml` declares `database_url: "sqlite:///somewhere.db"`
- **THEN** loading fails fast with a schema error naming the unknown field

### Requirement: Inline-secret rejection covers governance and deployment fields

The system SHALL extend inline-secret rejection to cover every secret-bearing field
introduced by the governance and deployment groups. Such credential values MUST be
provided as `*_env` environment-variable references and MUST NOT appear as inline
plaintext secrets, consistent with the existing guard over `mcp_servers`, `connectors`,
and the intelligence layer.

#### Scenario: Inline secret in a deployment field is rejected

- **WHEN** a governance/deployment field that carries credentials is given an inline
  secret-looking value instead of an `*_env` reference
- **THEN** loading fails fast with an inline-secret error naming the agent, field, and file

