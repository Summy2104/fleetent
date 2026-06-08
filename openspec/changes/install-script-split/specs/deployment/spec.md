# deployment Delta Spec

## ADDED Requirements

### Requirement: install scripts are separated by deployment role

The repository SHALL provide separate install scripts for agent-only and platform-only
deployment roles, in addition to the developer all-in-one script.

#### Scenario: Agent-only deployment uses install-agent.sh

- **WHEN** an operator needs to deploy only a standalone agent (no platform)
- **THEN** `scripts/install-agent.sh <agent-id>` SHALL be sufficient
- **AND** no platform DB or admin commands SHALL be required

#### Scenario: Platform-only deployment uses install-platform.sh

- **WHEN** an operator needs to deploy only the platform control plane
- **THEN** `scripts/install-platform.sh` SHALL be sufficient
- **AND** no agent home SHALL be created

#### Scenario: Developer all-in-one uses install.sh

- **WHEN** a developer runs `scripts/install.sh` locally
- **THEN** both agent and platform components SHALL be installed
- **AND** the binary SHALL be installed in editable mode
