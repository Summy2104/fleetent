## MODIFIED Requirements

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
