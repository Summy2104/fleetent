## MODIFIED Requirements

### Requirement: fleetent node start 守护与配置

系统 SHALL 提供 `fleetent node start`(`fleetent` 的 `node start` 子命令),作为跑在每个 agent host 上的长驻守护。它 SHALL 从配置读取:platform 基址、本 node 的 node-id、node service key(`ma-<hex>`)、`FLEETENT_HOME`、reconcile 轮询间隔。配置 SHALL 优先从 `$FLEETENT_HOME/node/.env` 加载(经 `load_dotenv(override=False)`:文件不存在则静默跳过;进程已有的环境变量优先于文件值),其余经环境变量(`FLEETENT_NODE_PLATFORM_URL` / `FLEETENT_NODE_ID` / `FLEETENT_NODE_SERVICE_KEY` / `FLEETENT_NODE_INTERVAL_SECONDS`)。`FLEETENT_HOME` SHALL 经进程环境提供(它是定位 node `.env` 的前提,不可经该 `.env` 设置)。`fleetent node start` SHALL 作为 platform HTTP API 的客户端运行,SHALL NOT `import fleetent.platform.*`,SHALL NOT `import` agent runtime 内部实现(仅经 subprocess 调用 agent CLI)。

#### Scenario: 守护启动并周期 reconcile

- **WHEN** `fleetent node start` 以有效配置启动
- **THEN** 它进入循环:按间隔拉取期望态 → reconcile → 上报实际态

#### Scenario: 从 node .env 加载配置

- **WHEN** `$FLEETENT_HOME/node/.env` 含 `FLEETENT_NODE_PLATFORM_URL` / `FLEETENT_NODE_ID` / `FLEETENT_NODE_SERVICE_KEY` 且这些变量未在进程环境中设置
- **THEN** `fleetent node start` 从该文件读取并成功启动

#### Scenario: 进程环境优先于 node .env

- **WHEN** 某变量同时存在于进程环境与 `$FLEETENT_HOME/node/.env`
- **THEN** 采用进程环境的值(`override=False`)

#### Scenario: node .env 缺失则回退进程环境

- **WHEN** `$FLEETENT_HOME/node/.env` 不存在
- **THEN** 加载步骤静默跳过,配置仅来自进程环境

#### Scenario: 缺失必需配置则拒绝启动

- **WHEN** 文件与进程环境均未提供 node-id 或 service key 或 platform 基址
- **THEN** `fleetent node start` 报错退出,不进入循环
