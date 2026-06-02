## ADDED Requirements

### Requirement: Pilot acceptance guide
部署文档 SHALL 提供测试环境 Pilot 人工验收指南，用于判断当前系统是否可以进入小范围真实用户试用。

#### Scenario: Acceptance guide exists
- **WHEN** operator 查找 Pilot 验收步骤
- **THEN** `docs/deployment/pilot-acceptance-guide.md` 存在
- **AND** 文档说明它用于安装完成后的人工验收

#### Scenario: Acceptance guide covers environment and configuration
- **WHEN** operator 按指南准备测试环境
- **THEN** 指南覆盖配置文件、secret、MCP server file、credential_ref、数据库路径和外部依赖检查

#### Scenario: Acceptance guide covers operational safety
- **WHEN** operator 按指南执行部署验收
- **THEN** 指南覆盖 SQLite backup、upgrade、backup-only、dry-run 和 restore drill

#### Scenario: Acceptance guide covers capability smoke checks
- **WHEN** operator 按指南执行功能验收
- **THEN** 指南覆盖 observability、diagnostics、memory、long-term context、reflection、knowledge base、vector reindex 和 embedding / rerank smoke

#### Scenario: Acceptance guide distinguishes skipped external smoke
- **WHEN** 真实 LLM、embedding、Google Drive 或 Confluence 凭据未配置
- **THEN** 指南要求把对应 smoke 记录为 skipped
- **AND** 不把显式未配置的外部依赖默认判定为验收失败

#### Scenario: Acceptance guide defines Go / No-Go
- **WHEN** 验收完成
- **THEN** 指南提供 Go、Conditional Go 和 No-Go 判定标准
- **AND** 指南提供问题记录和验收报告模板
