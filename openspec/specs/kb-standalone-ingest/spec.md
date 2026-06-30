# kb-standalone-ingest Specification

## Purpose
TBD - created by archiving change kb-standalone-ingest. Update Purpose after archive.
## Requirements
### Requirement: Standalone KB service config contract

KB 服务 standalone 部署 SHALL 从自己的配置文件(`$FLEETENT_HOME/kb-service/kb-service.yaml`)读取 ingest 与检索构造配置:service(tenant_id/host/port)、data(home)、retrieval(default_mode/rerank/top_k)、embedding(endpoint/model/dimensions)、extraction(enabled/endpoint/model)、chunking(chunk_size/chunk_overlap)、connectors(各源 type/kb_id/scope/`sync_interval_seconds`/`credential_ref`)。仓库 SHALL 提供根模板 `kb-service.yaml.example` 与 `kb-service.env.example`；系统 SHALL 提供 `fleetent kb-service init-config`,从这些 canonical example(经打包资源读取,不依赖 cwd)scaffold `$FLEETENT_HOME/kb-service/` 下的 `kb-service.yaml` 与 `.env`。

#### Scenario: 配置文件驱动连接器
- **WHEN** KB 服务以 standalone 模式启动并加载 `$FLEETENT_HOME/kb-service/kb-service.yaml`
- **THEN** 连接器定义来自该文件,经注入的 settings 提供给 `operations`(不来自 management.db)

#### Scenario: 提供 example 模板与 init-config
- **WHEN** 查看仓库并运行 `fleetent kb-service init-config`
- **THEN** 存在根 `kb-service.yaml.example` 与 `kb-service.env.example`
- **AND** 命令在 `$FLEETENT_HOME/kb-service/` 生成 `kb-service.yaml` 与 `.env`

#### Scenario: worker 与 serve 共用 kb-service 目录
- **WHEN** `fleetent kb-worker --config $FLEETENT_HOME/kb-service/kb-service.yaml` 与 `fleetent kb-serve --config $FLEETENT_HOME/kb-service/kb-service.yaml` 启动
- **THEN** 二者共用同一 `kb-service.yaml` 与同目录 `.env`

### Requirement: Local credential resolution

standalone KB 服务的连接器凭据 SHALL 在 **KB 主机本地**经 `credential_ref`(`env:NAME` / `file://PATH`)解析,真值 SHALL NOT 经网络下发。多个连接器 SHALL 可共用同一 `credential_ref`(指向同一 env)。

#### Scenario: 本地解析凭据
- **WHEN** worker 执行某连接器同步
- **THEN** 经其 `credential_ref` 在本地 env/file 解析真实凭据
- **AND** 真实凭据未经任何网络下发到本进程

#### Scenario: 连接器共用凭据
- **WHEN** 两个连接器的 `credential_ref` 指向同一 env 名
- **THEN** 二者共用该凭据,`.env` 只需一条

### Requirement: KB-local ingest queue, worker and sweep

standalone 模式下,ingest 队列 / worker / sweep SHALL 全在 KB 主机本地:worker 抽 **KB 本地**队列(非 management.db);sweep 由 KB 服务自己的调度器按配置文件 `sync_interval_seconds` 入队;**无需 platform 或 management.db**。

#### Scenario: 本地队列与 worker
- **WHEN** standalone KB 服务运行 ingest
- **THEN** job 入 KB 主机本地队列,由本地 worker 抽取执行,写本租户 `kb/`
- **AND** 不读写 management.db

#### Scenario: 服务自有 sweep
- **WHEN** 某连接器配了 `sync_interval_seconds` 且到期
- **THEN** KB 服务自己的调度器入队该连接器同步(不依赖 platform cron)

### Requirement: Boot validation of config and credentials

KB 服务启动 SHALL 校验配置完整性:所有连接器引用的 `credential_ref` 指向的 env/file SHALL 存在,embedding endpoint SHALL 配置;任一缺失 SHALL 启动即失败并指出缺项(不延迟到运行时才炸)。

#### Scenario: 缺凭据启动失败
- **WHEN** 某连接器 `credential_ref` 指向的 env/file 不存在
- **THEN** 服务启动失败并报出缺失的引用

#### Scenario: 配置齐全启动成功
- **WHEN** 所有引用就位、embedding 已配
- **THEN** 服务正常启动

### Requirement: Platform-optional operation

standalone KB 服务的 ingest 与检索 SHALL 能在**无 platform、management.db 不存在**的环境下完成;管理(改连接器/绑定)在该环境下不可用,但已配置的 ingest/检索 SHALL 继续运作。

#### Scenario: 无 platform 完成 ingest 与检索
- **WHEN** 环境无 platform、无 management.db,KB 服务按 `kb-service.yaml` 启动
- **THEN** connector sync / ingest / 检索均可完成
- **AND** 进程不因 management.db 缺失而失败

