## ADDED Requirements

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
