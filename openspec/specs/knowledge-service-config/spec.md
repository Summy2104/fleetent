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

### Requirement: Standalone KB config follows project env-ref conventions

standalone `kb-service.yaml` + `.env` 的密钥引用 SHALL 遵循全项目统一的 `*_env` / `*_ref` 引用范式与 `FLEETENT_*` 命名约定,与平台时代 KB 配置(`platform.yaml` 的 `knowledge` 段 + `.env`)一致;SHALL NOT 自创独立的命名体系或把多字段凭据塞成单个 JSON blob。YAML 只存 env 变量**名**引用,绝不含真实 secret。

- service key 经 `service.service_key_ref`(如 `env:FLEETENT_KB_SERVICE_KEY`)引用。
- 每个 connector 的凭据经粒度 `*_env` 字段引用(google_drive 用 `access_token_env` / `refresh_token_env` / `client_id_env` / `client_secret_env` / `token_uri_env`;confluence 用 `username_env` / `api_token_env`),env 名采用 `FLEETENT_*`(如 `FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN`、`FLEETENT_CONFLUENCE_TOKEN`)。
- embedding / extraction 经 `api_key_env` 引用密钥(如 `FLEETENT_KB_EMBEDDING_API_KEY` / `FLEETENT_KB_EXTRACTION_API_KEY`)。

#### Scenario: 凭据经粒度 env 字段引用
- **WHEN** kb-service.yaml 配置一个 google_drive 或 confluence connector
- **THEN** 其凭据经粒度 `*_env` 字段(`access_token_env` / `api_token_env` 等)引用 `FLEETENT_*` 命名的 env 变量
- **AND** 不出现内联 JSON blob 形式的凭据

#### Scenario: embedding/extraction 密钥经 api_key_env 引用
- **WHEN** kb-service.yaml 的 `embedding` / `extraction` section 需要调用带鉴权的端点
- **THEN** 该 section 经 `api_key_env` 字段引用 env 变量,服务从该 env 读取密钥并用于请求
- **AND** 该引用同时被 boot 校验覆盖(见 `kb-standalone-ingest` 的 Boot validation)

#### Scenario: 模板镜像项目范式
- **WHEN** 查看 `kb-service.yaml.example` 与 `kb-service.env.example`
- **THEN** 其 service key / connector / embedding / extraction 的引用形态与命名,与平台时代 KB 配置范式一致(`FLEETENT_*` + `*_env`)

