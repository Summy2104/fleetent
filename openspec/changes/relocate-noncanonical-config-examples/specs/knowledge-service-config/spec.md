## MODIFIED Requirements

### Requirement: Knowledge service config file

The platform/KB service SHALL read KB construction configuration from
`<FLEETENT_HOME>/config/knowledge.yaml` by default. When the KB service is deployed separately,
the same contract SHALL be materialized to `<knowledge-service-home>/config/knowledge.yaml`.
Repository templates for this optional standalone deployment SHALL be examples, not active
default config templates, and SHALL live under `examples/knowledge-service/`.

#### Scenario: Default platform path
- **WHEN** the platform runtime loads KB construction config
- **THEN** it reads `<FLEETENT_HOME>/config/knowledge.yaml`

#### Scenario: Service path
- **WHEN** KB service is deployed as a standalone service
- **THEN** it uses `<knowledge-service-home>/config/knowledge.yaml`

#### Scenario: Standalone templates are examples
- **WHEN** 查看仓库模板
- **THEN** standalone Knowledge Service 示例位于 `examples/knowledge-service/`
- **AND** 不位于 active `config/knowledge-service/`
