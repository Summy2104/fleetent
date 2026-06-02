## ADDED Requirements

### Requirement: Pilot connector operation guidance
部署文档 SHALL 说明 Pilot 环境中如何配置、检查、手动同步和排查 knowledge-base connectors。

#### Scenario: Connector CLI commands are documented
- **WHEN** operator 阅读部署或运维文档
- **THEN** 文档列出 `fleetent-admin kb connectors list/check/status/sync` 的用途

#### Scenario: Credential boundary is documented
- **WHEN** operator 阅读部署或运维文档
- **THEN** 文档说明真实 credential 不应写入 `settings.yaml`
- **AND** 文档说明 `credential_ref` 指向的文件或环境变量需要由部署方保护权限

#### Scenario: Connector troubleshooting is documented
- **WHEN** connector check 或 sync 返回 credential_missing、auth_failed、scope_unreachable 或 sync_failed
- **THEN** 文档提供对应的排查方向
