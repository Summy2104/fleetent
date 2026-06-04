## MODIFIED Requirements

### Requirement: Secrets stay outside settings YAML
敏感值 SHALL 继续通过环境变量或 `.env` 注入，而不是写入 `config/settings.yaml` 或
`agent.yaml`。

#### Scenario: Secret references use env names
- **WHEN** 某 provider 需要 API key
- **THEN** 配置文件只保存 `api_key_env` 或等价 env var 名称，不保存 secret value

#### Scenario: Settings example is not required for deployed agent
- **WHEN** 查看部署模板
- **THEN** `config/settings.yaml.example` 不需要存在
- **AND** 部署 agent 的非敏感示例配置位于 `config/agent.yaml.example`
