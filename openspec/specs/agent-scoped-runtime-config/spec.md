# agent-scoped-runtime-config Specification

## Purpose
TBD - created by archiving change runtime-read-agent-config. Update Purpose after archive.
## Requirements

### Requirement: Per-run governance resolved from the active agent snapshot

The system SHALL resolve per-run governance configuration (context compression, layered
budget on the `session`/`user`/`agent` dimensions, loop/budget/guardrail controls,
permission gate timeouts, provider circuit breaker, default tool timeout, sub-agent
timeout) from the agent configuration carried by the request's resolved `AgentSnapshot`,
rather than from the global `Settings`. The `AgentSnapshot` for a file-sourced agent
SHALL be populated from its `AgentFile`. Resolution precedence MUST be: explicit call
parameter > agent configuration > field default.

#### Scenario: max_turns comes from agent config when no call override

- **WHEN** an agent whose `agent.yaml` declares `agent_max_turns: 30` runs with no
  explicit `max_turns` call parameter
- **THEN** the run's iteration budget is 30

#### Scenario: call parameter overrides agent config

- **WHEN** the same agent runs with an explicit `max_turns=5` call parameter
- **THEN** the run's iteration budget is 5, taking precedence over the agent config value

#### Scenario: omitted field falls back to the prior default

- **WHEN** an agent's `agent.yaml` declares no `tool_default_timeout_seconds`
- **THEN** the resolved default tool timeout equals the prior `Settings` default (30.0s)

### Requirement: Process-level deployment knobs resolved at agent startup

The system SHALL resolve process-level deployment knobs (session disk cleanup interval,
`disabled_skills`, logging/observability, the `sandbox` section (backend selection),
image/vision endpoints, diagnostics) for a standalone agent process from the current
(single) active agent's configuration at process startup, rather than from the global
`Settings`. In the multi-agent dev/platform mode where no single agent owns the process,
these knobs SHALL fall back to their defaults.

#### Scenario: standalone agent applies its own session cleanup interval

- **WHEN** a standalone `fleetent agent run` process starts for an agent whose `agent.yaml`
  declares `session_cleanup_interval_seconds: 600`
- **THEN** the internal maintenance loop uses a 600s interval

#### Scenario: standalone agent applies its own disabled_skills

- **WHEN** a standalone agent process starts for an agent declaring `disabled_skills: ["x"]`
- **THEN** skill `x` is excluded from that process's skill registry

#### Scenario: standalone agent resolves its sandbox backend from agent.yaml

- **WHEN** a standalone agent process starts for an agent whose `agent.yaml` declares
  `sandbox.backend: microsandbox`
- **THEN** the process selects the microsandbox backend from that agent-level configuration,
  without reading any platform-level settings file

### Requirement: Global budget dimension is not read at runtime

The system SHALL NOT read or enforce any retired cross-run budget dimension at runtime.
No runtime path SHALL consult legacy cross-run budget config fields.

#### Scenario: runtime ignores retired cross-run budget dimensions

- **WHEN** the cross-run layered budget aggregation runs
- **THEN** it evaluates only the `session`, `user`, and `agent` scopes and never a `global`
  scope

### Requirement: Intelligence layer reads the active agent's configuration

The system SHALL construct the intelligence subsystems — vector store, embedding, rerank,
knowledge base, long-term context, memory, and reflection — from the active agent's
configuration rather than from the global `Settings` intelligence sub-config. This
eliminates the previously parsed-but-unused agent-file intelligence fields.

#### Scenario: embedding backend comes from the agent config

- **WHEN** an agent's `agent.yaml` declares an `embedding` block and the agent runs
- **THEN** the embedding backend is constructed from that agent-config block, not from the
  global `Settings.embedding`
