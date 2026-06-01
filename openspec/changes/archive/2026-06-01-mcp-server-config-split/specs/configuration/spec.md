## MODIFIED Requirements

### Requirement: Minimal settings surface
第一版统一配置 SHALL 只包含当前明确需要的顶层 namespace。

#### Scenario: Supported settings namespaces
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** 文件只包含 database_url、log_format、observability、mcp、scheduling、webhooks、
  vector_store、embedding、rerank、knowledge_base 和 long_term_ctx

#### Scenario: Runtime objects stay out of settings
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** 文件不包含 cron jobs、webhook sources、MCP server definitions、agent definitions、
  user bindings、memory items、knowledge documents 或 reindex jobs

#### Scenario: MCP settings are global policy only
- **WHEN** 查看 `config/settings.yaml.example`
- **THEN** `mcp` namespace 只包含全局策略字段，不包含 `servers`
