## MODIFIED Requirements

### Requirement: Process-level deployment knobs resolved at agent startup

The system SHALL resolve process-level deployment knobs (session disk cleanup interval,
`disabled_skills`, logging/observability, diagnostics) for a standalone agent process
from the current (single) active agent's configuration at process startup, rather than
from the global `Settings`. In the multi-agent dev/platform mode where no single agent
owns the process, these knobs SHALL fall back to their defaults.

Image and vision endpoints SHALL be configured exclusively via `models.targets` and
`models.routes` in `agent.yaml`; there are no separate `image_gen_url`, `image_gen_model`,
`vision_url`, or `vision_model` top-level fields. The sandbox backend is Docker and has
no agent-level URL configuration; there is no `microsandbox_url` field.

#### Scenario: standalone agent applies its own session cleanup interval

- **WHEN** a standalone `fleetent agent run` process starts for an agent whose `agent.yaml`
  declares `session_cleanup_interval_seconds: 600`
- **THEN** the internal maintenance loop uses a 600s interval

#### Scenario: standalone agent applies its own disabled_skills

- **WHEN** a standalone agent process starts for an agent declaring `disabled_skills: ["x"]`
- **THEN** skill `x` is excluded from that process's skill registry

#### Scenario: agent.yaml with removed fields is rejected at load time

- **WHEN** an `agent.yaml` contains any of `microsandbox_url`, `image_gen_url`,
  `image_gen_model`, `vision_url`, or `vision_model`
- **THEN** loading the file raises a validation error (Pydantic `extra="forbid"`)

## REMOVED Requirements

### Requirement: image/vision endpoint fields in AgentFile

**Reason**: `image_gen_url`, `image_gen_model`, `vision_url`, `vision_model` were
superseded by the `models.targets` + `models.routes` system. The runtime clients
(`image_gen_client`, `vision_client`) now resolve endpoints through `ModelPolicySnapshot`
and have never read these top-level fields in practice.

**Migration**: Configure image generation via `models.targets` with
`protocol: openai_image_generation` and `models.routes["image_generation"]`. Configure
vision via `models.targets` with `protocol: openai_chat` and `models.routes["vision"]`.

### Requirement: microsandbox_url field in AgentFile

**Reason**: The sandbox backend is Docker (direct CLI). A microsandbox HTTP endpoint
was planned but not implemented; the field was never read by any runtime code.

**Migration**: No replacement. Sandbox configuration is handled at the Docker level.
