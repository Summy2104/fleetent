## ADDED Requirements

### Requirement: Knowledge service config file

The platform/KB service SHALL read KB construction configuration from
`<FLEETENT_HOME>/config/knowledge.yaml` by default. When the KB service is deployed separately,
the same contract SHALL be materialized to `<knowledge-service-home>/config/knowledge.yaml`.

#### Scenario: Default platform path
- **WHEN** the platform runtime loads KB construction config
- **THEN** it reads `<FLEETENT_HOME>/config/knowledge.yaml`

#### Scenario: Service path
- **WHEN** KB service is deployed as a standalone service
- **THEN** it uses `<knowledge-service-home>/config/knowledge.yaml`

### Requirement: Knowledge bases contain unified sources

`knowledge.yaml` SHALL define `knowledge_bases[]`. Each KB entry SHALL include `id`,
`tenant_id`, and MAY include `indexing`, `sync`, and unified `sources[]`. Each source SHALL
have `id`, `type`, `enabled`, and type-specific non-secret fields. Secrets SHALL be referenced
by env var names or credential references only.

#### Scenario: Google Drive source
- **WHEN** a source has `type: google_drive`
- **THEN** it must provide Google Drive scope fields such as `folder_id`
- **AND** credential values are referenced by env fields such as `access_token_env`

#### Scenario: Confluence source
- **WHEN** a source has `type: confluence`
- **THEN** it must provide `base_url` and a scope such as `space_key` or `page_id`
- **AND** credential values are referenced by env fields such as `api_token_env`

#### Scenario: Source ids are unique
- **WHEN** two sources in the deployment have the same `id`
- **THEN** config loading fails loudly

### Requirement: KB operations use knowledge config

KB connector listing, checking, dry-run, sync, and status operations SHALL use the validated
knowledge service config/snapshot as the source of connector/source definitions.

#### Scenario: List configured sources
- **WHEN** KB operations list configured connectors/sources
- **THEN** the result is derived from `knowledge.yaml` `knowledge_bases[].sources[]`

#### Scenario: Source status is scoped
- **WHEN** a source sync records latest status
- **THEN** the status includes source id, source type, tenant_id, and kb_id

