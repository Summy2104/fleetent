## Context

完全平行 `node-config-file`(已落地):node 从 `$FLEETENT_HOME/node/.env` 加载;kb-worker 从 `$FLEETENT_HOME/kb-worker/.env` 加载。范式同 `agent_app.py:381-385`(`load_dotenv(override=False)`,存在才加载)。

## Goals / Non-Goals

**Goals:** kb-worker 从专属 `.env` 加载自身配置(队列/底座/embedder/Vault 接入);加模板;明确 connector 配置不在此。

**Non-Goals:** 不把 connector 配置塞进 worker 配置(控制面 per-job);不把 `FLEETENT_HOME` 放进该 `.env`(鸡生蛋);不碰队列/底座实现。

## Decisions

### D1:加载顺序(同 node)

worker 启动:解析 `FLEETENT_HOME`(进程 env or 默认)→ `load_dotenv($FLEETENT_HOME/kb-worker/.env, override=False)`(存在才加载)→ 读自身配置项。`override=False` 保证 systemd/容器注入优先。`FLEETENT_HOME` 只从进程 env(它是定位该 `.env` 的前提)。

### D2:自身配置项范围

- 队列连接(读 `kb_ingest_jobs` 的库连接)
- 数据底座连接(写 KB 的目标;单机=本地文件路径,分布式=网络 DB——后端可插拔由后续 substrate change 决定,本 change 只读"连接信息")
- embedder 配置(provider/endpoint/model;embedder 凭据可走 Vault 或此处)
- Vault 接入(worker 作为 principal 解析 connector 凭据 ref 用)

### D3:connector 配置显式排除

模板与 spec 显式声明:**connector 配置(源地址/参数/凭据)不进 worker 配置**——它是控制面注册表 + Vault,per-job 随 job 下发。worker 自身配置只装"怎么当一个 worker"的静态连接信息。

## Risks / Trade-offs

- **[Vault 接入凭据落 worker .env]** worker 的 Vault 接入凭据在该文件——与 node service key 同性质;权限 0600,模板注明。
- **[底座连接与后续 substrate change 的衔接]** 本 change 只读"底座连接信息";具体后端(本地↔网络)由后续 `agent-data-substrate-pluggable` 决定,字段命名留余地。
