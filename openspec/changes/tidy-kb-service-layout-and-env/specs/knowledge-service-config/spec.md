## ADDED Requirements

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
