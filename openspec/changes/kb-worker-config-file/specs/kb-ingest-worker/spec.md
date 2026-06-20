## ADDED Requirements

### Requirement: kb-worker 从专属 .env 加载自身配置

`fleetent kb-worker` 启动 SHALL 从 `$FLEETENT_HOME/kb-worker/.env` 加载自身配置(经 `load_dotenv(override=False)`:文件不存在静默跳过;进程已有环境变量优先于文件值)。自身配置 SHALL 含:队列连接、数据底座连接、embedder 配置、Vault 接入。`FLEETENT_HOME` SHALL 经进程环境提供(定位该 `.env` 的前提,不可经该 `.env` 设置)。

#### Scenario: 从 .env 加载

- **WHEN** `$FLEETENT_HOME/kb-worker/.env` 含队列/底座/embedder/Vault 接入配置,且未在进程环境设置
- **THEN** worker 从该文件读取并成功启动

#### Scenario: 进程环境优先

- **WHEN** 某项同时存在于进程环境与该 `.env`
- **THEN** 采用进程环境的值(override=False)

#### Scenario: 文件缺失回退进程环境

- **WHEN** 该 `.env` 不存在
- **THEN** 加载步骤静默跳过,配置仅来自进程环境

### Requirement: connector 配置不在 worker 自身配置内

worker 自身配置 SHALL 只含部署级静态连接信息(队列/底座/embedder/Vault 接入)。connector 配置(源地址/参数/凭据)SHALL NOT 出现在 worker 自身配置文件中——它由 Platform 注册表 + Vault 持有,随 job 下发。

#### Scenario: worker 配置不含 connector

- **WHEN** 检视 `kb-worker.env.example` 与 worker 配置加载
- **THEN** 不含任何具体 connector 的源地址/参数/凭据;这些经 job 下发
