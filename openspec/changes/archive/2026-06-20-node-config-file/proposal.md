## Why

`fleetent node start` 的配置(platform 基址、node-id、service key、轮询间隔)目前**只从裸环境变量读**(`node/config.py` 的 `_require_env`),没有任何项目级文件约定——部署时必须靠 systemd `EnvironmentFile` / shell export / Docker `--env-file` 把变量塞进进程环境。这与 agent home 的 `.env` 约定(`agent_app` 用 `load_dotenv(override=False)` 加载 `<home>/.env`)不一致,也让 node 身份(尤其 service key 密钥)散落、不可发现。

node 跑在 **agent 宿主**(非 platform 宿主),其配置是该机器的部署配置,既不属于 platform、也不属于任何单个 agent(node 监管多个 agent)。它应有**专属配置文件**。

## What Changes

- **node 加载专属 `.env`**:`node/config.py` 的 `load_config()` SHALL 在读 `FLEETENT_NODE_*` 前,从 `$FLEETENT_HOME/node/.env` 经 `load_dotenv(override=False)` 加载(文件不存在则静默跳过;进程已有的环境变量优先)。完全对齐 agent home `.env` 的加载范式。
- **新增模板** `config/node.env.example`:含 `FLEETENT_NODE_PLATFORM_URL` / `FLEETENT_NODE_ID` / `FLEETENT_NODE_SERVICE_KEY` / `FLEETENT_NODE_INTERVAL_SECONDS`,供复制到 `$FLEETENT_HOME/node/.env`。
- **修正 spec 过时措辞**:node-supervisor「fleetent node start 守护与配置」把"新 console-script"改为"`fleetent` 子命令"(node 已收成 `fleetent node start`,独立 binary 早已移除)。

**不动**:`FLEETENT_HOME` 仍由进程环境提供(它要先于 node `.env` 解析出来才能定位该文件,不能放进 node `.env`);node 不属于 platform/agent 的配置层;不碰 desired-state/secret 注入(密钥仍由 platform 下发、不落盘)。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities

- `node-supervisor`:MODIFY「fleetent node start 守护与配置」——新增从 `$FLEETENT_HOME/node/.env` 加载配置(进程 env 优先、缺失静默跳过);修正入口措辞为子命令。

## Impact

**owning package**:`src/fleetent/node/config.py`(加 `.env` 加载);新增 `config/node.env.example`

**public API surface**:无(`load_config()` 签名不变,仅新增文件加载步骤)

**owned tables**:无　**config namespace**:`FLEETENT_NODE_*`(不变,新增文件来源)　**migration**:无

**cross-module dependencies**:无;`node/config.py` 新增对 `python-dotenv` 的 import(已是依赖,agent_app 在用)

**配置归属边界**:node 配置(身份 + platform 连接)= agent 宿主本地、专属文件 `$FLEETENT_HOME/node/.env`;agent 配置/密钥仍由 platform materialize 下发(node 落地 agent.yaml + 注入 secret env,不落盘)。
