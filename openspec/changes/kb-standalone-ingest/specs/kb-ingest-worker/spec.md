## MODIFIED Requirements

### Requirement: connector 配置不在 worker 自身配置内

本要求适用于**平台托管(platform-managed)**部署模式:此模式下 worker 自身配置 SHALL 只含部署级静态连接信息(队列/底座/embedder/Vault 接入);connector 配置(源地址/参数/凭据)SHALL NOT 出现在 worker 自身配置文件中——它由 Platform 注册表 + Vault 持有,随 job 下发。**standalone 部署模式**(见 `kb-standalone-ingest`)是另一形态:KB 服务从自己的 `kb-service.yaml` 持有 connector 配置、在本地解析凭据,不依赖 Platform 下发。

#### Scenario: 平台托管模式 worker 配置不含 connector

- **WHEN** 平台托管模式下检视 `kb-worker.env.example` 与 worker 配置加载
- **THEN** 不含任何具体 connector 的源地址/参数/凭据;这些经 job 下发

#### Scenario: standalone 模式连接器配置在 KB 服务

- **WHEN** standalone 模式下 KB 服务运行 ingest
- **THEN** connector 配置来自 KB 服务的 `kb-service.yaml`,凭据在 KB 主机本地按 `credential_ref` 解析
- **AND** 不依赖 Platform 注册表 / job 下发
