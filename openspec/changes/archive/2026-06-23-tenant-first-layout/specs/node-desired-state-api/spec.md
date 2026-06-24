## ADDED Requirements

### Requirement: Desired-state includes tenant-aware home inputs

`GET /nodes/{node-id}/desired-state` SHALL include enough information for node to resolve each managed agent's tenant-aware home, including platform `agent_id`, stable `name`, `tenant_id`, non-secret agent config, and secrets/env values partitioned for that agent.

#### Scenario: Desired agent carries tenant id
- **WHEN** platform returns desired-state for node `local-node`
- **THEN** each agent entry includes `tenant_id`
- **AND** node can derive `tenants/<tenant_id>/agents/<name>/` without querying management DB directly

### Requirement: Desired-state includes skill manifests

desired-state SHALL include a skill manifest for each skill that node must deploy for the agent. The manifest SHALL include `name`, `base_version`, `base_commit`, `bundle_url`, and `bundle_sha256`; it SHALL NOT inline arbitrary file contents.

#### Scenario: Enabled skill appears as manifest entry
- **WHEN** agent `support` has enabled skill `foo`
- **THEN** desired-state for `support` includes a manifest entry for `foo`
- **AND** the entry contains version and bundle verification metadata

#### Scenario: Disabled skill does not require bundle deployment
- **WHEN** a globally disabled skill is present in the public pool
- **THEN** desired-state may include it in `disabled_skills` for agent.yaml
- **AND** node is not required to deploy its bundle for runtime use

### Requirement: Desired-state cache strips secret and bundle payload contents

node's desired-state cache SHALL NOT store plaintext secret values beyond the `.env` scaffold responsibility, and SHALL NOT cache full skill bundle file contents inside `desired-state-cache.json`. It MAY cache skill manifest metadata.

#### Scenario: Cache contains manifest not bundle contents
- **WHEN** node caches desired-state locally
- **THEN** cache contains skill names and version metadata
- **AND** cache does not contain `SKILL.md` contents or packed bundle bytes
