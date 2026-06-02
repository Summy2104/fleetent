## ADDED Requirements

### Requirement: Knowledge-base connector configuration
系统 SHALL 支持在统一应用配置中声明 knowledge-base connector definitions，且只保存非 secret 字段和 credential references。

#### Scenario: Google Drive connector config shape
- **WHEN** `settings.yaml` 配置 Google Drive connector
- **THEN** 配置包含 connector_id、enabled、tenant_id、kb_id、folder_id、recursive 和 credential_ref

#### Scenario: Confluence connector config shape
- **WHEN** `settings.yaml` 配置 Confluence connector
- **THEN** 配置包含 connector_id、enabled、tenant_id、kb_id、base_url、username、scope 字段和 credential_ref

#### Scenario: Config stores credential reference only
- **WHEN** `settings.yaml` 配置任意 knowledge-base connector
- **THEN** 配置只包含 `credential_ref`
- **AND** 不包含 OAuth refresh token、client secret、Confluence API token 或其他真实 credential payload

#### Scenario: Credential ref supports file and env
- **WHEN** connector 配置 `credential_ref`
- **THEN** 系统支持 `file://...`、本地文件路径和 `env:VAR_NAME` 引用形式
