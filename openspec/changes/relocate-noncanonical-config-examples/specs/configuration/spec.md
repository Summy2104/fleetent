## MODIFIED Requirements

### Requirement: Canonical templates avoid ambiguous agent paths

仓库 canonical 模板 SHALL 清楚区分 Platform 与 Agent 模板。`config/` SHALL only contain active
canonical deployment templates for the default MVP deployment: `config/platform/` and `config/agent/`.
Noncanonical test fixtures SHALL live outside `config/`. Optional standalone service examples SHALL
NOT be shipped for services that are not supported as independent deployment targets in the current
stage. Tracked concrete local files such as `config/agent.yaml` SHALL NOT be presented as canonical
templates.

#### Scenario: Canonical templates are discoverable
- **WHEN** 查看仓库配置模板
- **THEN** 能区分 Platform YAML/ENV 模板与 Agent YAML/ENV 模板
- **AND** 不需要通过 `agent` / `agents` 单复数差异理解部署语义

#### Scenario: Multi-agent scan examples are not deployment templates
- **WHEN** 文档描述部署模板
- **THEN** 不把 `config/agents/<name>/agent.yaml.example` 描述为默认部署模板

#### Scenario: Active config excludes noncanonical examples
- **WHEN** 查看仓库 `config/` 目录
- **THEN** 只存在 `config/agent/` 与 `config/platform/`
- **AND** 不存在 `config/agents/` 或 `config/knowledge-service/`
