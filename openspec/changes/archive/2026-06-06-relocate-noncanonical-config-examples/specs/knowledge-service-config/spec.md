## MODIFIED Requirements

### Requirement: Knowledge service config file

The platform/KB service SHALL read KB construction configuration from
`<FLEETENT_HOME>/config/knowledge.yaml` by default. When the KB service is deployed separately,
the same contract SHALL be materialized to `<knowledge-service-home>/config/knowledge.yaml`.
Repository templates for this optional standalone deployment SHALL NOT be shipped in the current
MVP stage. Future standalone deployment templates MAY be introduced by a separate change when the
service is actually supported as an independent deployment target.

#### Scenario: Default platform path
- **WHEN** the platform runtime loads KB construction config
- **THEN** it reads `<FLEETENT_HOME>/config/knowledge.yaml`

#### Scenario: Service path
- **WHEN** KB service is deployed as a standalone service
- **THEN** it uses `<knowledge-service-home>/config/knowledge.yaml`

#### Scenario: Standalone templates are deferred
- **WHEN** 查看仓库模板
- **THEN** 不存在 active `config/knowledge-service/`
- **AND** 不存在 `examples/knowledge-service/`
- **AND** standalone Knowledge Service 模板不作为当前阶段 setup requirement
