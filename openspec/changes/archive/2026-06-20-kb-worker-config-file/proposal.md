## Why

`kb-worker` 落地后,worker 的自身配置(队列连接、数据底座连接、embedder、Vault 接入)若只从裸环境变量读,会重蹈 node 的覆辙——无文件约定、散落、密钥相关项不可控。本 change 给 kb-worker 一个**专属配置文件**,与 `node-config-file` 完全平行:`$FLEETENT_HOME/kb-worker/.env`,`load_dotenv(override=False)`(进程 env 优先、缺失静默跳过)。

**前置**:`kb-worker` 已落地。

## What Changes

- **kb-worker 加载专属 `.env`**:worker 启动读 `$FLEETENT_HOME/kb-worker/.env`(`load_dotenv(override=False)`),再读自身配置项:队列连接、数据底座连接、embedder 配置、Vault 接入。
- **新增模板** `config/kb-worker.env.example`:含上述项,注释说明 `FLEETENT_HOME` 须经进程 env、权限 0600、Vault 接入用途。
- **明确边界**:**connector 配置不在此文件**(那是控制面 per-job 下发);worker 自身配置 = 部署级静态连接信息。

**不动**:connector 注册表(Platform 管理库)、凭据(Vault)、job 队列;`FLEETENT_HOME` 仍经进程 env(定位 `.env` 的前提)。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `kb-ingest-worker`:新增"从 `$FLEETENT_HOME/kb-worker/.env` 加载自身配置(进程 env 优先、缺失静默跳过);connector 配置不在自身配置内"的要求。

## Impact

**owning package**:`knowledge_base/ingest`(worker 配置加载)+ 新增 `config/kb-worker.env.example`

**public API surface**:无　**owned tables**:无　**config namespace**:`FLEETENT_HOME/kb-worker/.env`(新文件来源,变量含队列/底座/embedder/Vault 接入)　**migration**:无

**cross-module dependencies**:无新增;复用 `python-dotenv`(已是依赖)

**边界**:worker 自身配置(静态连接)vs connector 配置(控制面 per-job)——两者分离,平行 `node-config-file`(见 [target-architecture §12 connector 三层归属])。
