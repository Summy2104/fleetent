# knowledge-service-config Specification

## Purpose
TBD - created by archiving change split-agent-knowledge-config. Update Purpose after archive.
## Requirements
### Requirement: Knowledge service config file

Default MVP deployment SHALL treat Knowledge as embedded in the Platform service. Embedded
Knowledge construction config SHALL be read from Platform config (`platform.yaml`) and/or Platform
DB managed connector state. The default deployment SHALL NOT read or materialize
legacy Knowledge YAML files. **当 Knowledge 以 standalone 服务部署时,该服务 SHALL 定义自己的 service home 与 config 契约(`kb-service.yaml` + `.env`,见 `kb-standalone-ingest`),从该文件读取连接器/检索/模型/分块构造配置,并可在无 platform 环境下运作。** 嵌入式(platform 内)与 standalone(独立服务)是两种部署形态:嵌入式从 platform 配置/DB 取构造配置,standalone 从自己的 `kb-service.yaml` 取。

#### Scenario: Embedded knowledge uses Platform config
- **WHEN** the platform runtime loads embedded KB construction config
- **THEN** it reads the `knowledge` section from `platform.yaml` or the Platform DB snapshot
- **AND** it does not require a standalone Knowledge YAML file

#### Scenario: Standalone service uses its own config contract
- **WHEN** Knowledge 以 standalone 服务部署
- **THEN** 它从自己的 `kb-service.yaml` + `.env` 读取连接器/检索/模型/分块配置
- **AND** 不依赖 platform 配置或 management.db 即可构造 ingest/检索

#### Scenario: Standalone templates are provided
- **WHEN** 查看仓库模板
- **THEN** 存在 `kb-service.example.yaml` 与配套 `.env.example`(standalone KB 服务模板)

### Requirement: Knowledge bases contain unified sources

Platform Knowledge config SHALL define embedded KB construction as `knowledge.knowledge_bases[]`
when expressed in `platform.yaml`. Each KB entry SHALL include `id`, `tenant_id`, and MAY include
`indexing`, `sync`, and unified `sources[]`. Each source SHALL have `id`, `type`, `enabled`, and
type-specific non-secret fields. Secrets SHALL be referenced by env var names or credential
references only.

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

KB connector listing, checking, dry-run, sync, and status operations SHALL use a validated
Knowledge config/snapshot supplied by Platform config or Platform DB managed connector state.

#### Scenario: List configured sources from Platform snapshot
- **WHEN** KB operations list configured connectors/sources
- **THEN** the result is derived from the active Platform Knowledge snapshot
- **AND** the default source is not a standalone Knowledge YAML file

### Requirement: Knowledge config follows deployment boundary

Knowledge / memory / vector / indexing 配置 SHALL 默认属于 Platform side when deployed together with the
Platform service. 独立 `knowledge.yaml + .env` SHALL only be required when Knowledge is deployed as a
separate service.

#### Scenario: Embedded knowledge uses Platform config
- **WHEN** Knowledge 与 Platform 一起部署
- **THEN** 不要求存在独立 `knowledge.yaml`
- **AND** Knowledge 构建、索引、connector 配置归入 Platform config/env

#### Scenario: Remote knowledge uses service config
- **WHEN** Knowledge 作为独立服务部署
- **THEN** Knowledge service 拥有自己的 `knowledge.yaml` 和 `.env`
- **AND** Platform config 只保存连接该服务所需的 endpoint 和 auth env 引用

