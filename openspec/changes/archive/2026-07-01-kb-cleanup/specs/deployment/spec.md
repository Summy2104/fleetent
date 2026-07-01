## MODIFIED Requirements

### Requirement: Pilot connector operation guidance
部署文档 SHALL 说明 Pilot 环境中如何配置、检查、手动同步和排查 knowledge-base connectors。实体抽取的手动入口 SHALL 指向独立命令 `fleetent kb-extract`（纯 KB 服务侧、入队经 kb-worker 消费），文档 SHALL NOT 再引用已退役的 `fleetent platform kb extract-entities`。

#### Scenario: Connector CLI commands are documented
- **WHEN** operator 阅读部署或运维文档
- **THEN** 文档列出 `/admin/kb/connectors/*` 的用途
- **AND** 文档以 `fleetent kb-extract` 说明手动实体抽取入口
- **AND** 文档不引用 `fleetent platform kb extract-entities`

#### Scenario: Credential boundary is documented
- **WHEN** operator 阅读部署或运维文档
- **THEN** 文档说明真实 credential 不应写入 YAML config
- **AND** 文档说明 `credential_ref` 指向的文件或环境变量需要由部署方保护权限

#### Scenario: Connector troubleshooting is documented
- **WHEN** connector check 或 sync 返回 credential_missing、auth_failed、scope_unreachable 或 sync_failed
- **THEN** 文档提供对应的排查方向
