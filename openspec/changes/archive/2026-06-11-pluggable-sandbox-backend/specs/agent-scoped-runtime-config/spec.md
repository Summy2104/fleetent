# agent-scoped-runtime-config（delta）

## MODIFIED Requirements

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
