## MODIFIED Requirements

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
