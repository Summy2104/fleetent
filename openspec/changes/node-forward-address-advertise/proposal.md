## Why

托管链路下 platform 经 admin chat / WS 转发到 node forwarder 时，目标地址由 `node/forwarder_contract.py` 固定拼成 `http://{node_id}.internal:8786`（除非设全局 env `FLEETENT_FORWARDER_HOST_OVERRIDE`）。platform **不持有任何 node 的真实可达地址**——它把"`{node_id}.internal` 如何解析"完全甩给部署环境的外部 DNS。

现实部署里这层 DNS 不存在：生产 `fleetent.elevatesphere.com` 上 platform 与 node 同机，`POST /admin/agents/dev/chat` 转发到 `local-node.internal:8786` 时 `getaddrinfo` 直接失败（`httpx.ConnectError: [Errno -2] Name or service not known`），chat 返回 500。dev agent 本身存活健康、模型供应商与 `agent.yaml` 均正常——纯粹是转发寻址断在 DNS。

现有两个绕法都不通用：
- **全局 `FLEETENT_FORWARDER_HOST_OVERRIDE`**：env 全局生效，会把**所有** node 的转发都打到同一个 host，与「一个 agent 可绑多个 node、node 分散在多台机器」的拓扑直接冲突。
- **手工维护 `/etc/hosts` / 内网 DNS**：每新增一台 node 都要人工在所有 platform 机登记 `<node_id>.internal → IP`，要求每个部署环境自备可管理的 DNS 运维能力，违背「跨服务器即插即用」目标。

根因是**地址来源缺失**：系统从不让 node 告知 platform 自己怎么被拨通。本 change 让 node 自报可达地址，platform 持久化并据此转发，彻底移除对外部 DNS 的依赖。

## What Changes

- **node 自报可达地址**：node 端读取**可选**环境变量 `FLEETENT_NODE_ADVERTISE_HOST`（该机对 platform 可达的 IP 或主机名；一机一 node，即这台机的地址），在既有 `POST /nodes/{id}/status` 心跳 payload 中以 `forward_host` 字段上报。未设则不上报（向前兼容）。
- **platform 持久化地址**：`nodes` 表 SHALL 新增列 `forward_host`（nullable TEXT，Alembic 维护）；status 端点收到心跳带 `forward_host` 时 SHALL upsert 到该 node 行。地址随心跳刷新（网络变更自愈）。
- **转发寻址改为按 node 查地址**：platform 拨 node forwarder（`platform/node_management/agent_transport.py`）时，目标 host 解析优先级 SHALL 为 **`nodes.forward_host`（已上报）→ `FLEETENT_FORWARDER_HOST_OVERRIDE`（env）→ `{node_id}.internal`（约定兜底）**。端口与协议（8786 / http+ws）不变。
- **收益**：每台新 node 部署只需配一个 `FLEETENT_NODE_ADVERTISE_HOST=<本机可达地址>`，注册上报后 platform 自动会转发——零外部 DNS 依赖、即插即用，天然支持 agent↔node 多对多多机；未上报地址的旧 node 回落约定/override，不破坏现状。

## Capabilities

### New Capabilities
<!-- 无新增 capability；复用既有 agent-node-registry / node-supervisor -->

### Modified Capabilities
- `agent-node-registry`：①MODIFY「node 注册表与身份」——`nodes` 表新增 `forward_host` 列，记录 node 自报的、供 platform 出站拨号的可达地址；②新增 requirement——platform→node 转发寻址按「持久化地址 → env override → `.internal` 约定」优先级解析。
- `node-supervisor`：新增 requirement——node 在 status 心跳上报自身 advertise host（来自 `FLEETENT_NODE_ADVERTISE_HOST`，未设则不上报）。

## Impact

- **owning package**：`node/`（`config.py`、`reconcile.py`）+ `platform/`（`node_management/node_store.py`、`node_management/node_desired_state_api.py`、`node_management/agent_transport.py`）+ `migrations/`（Alembic）。
- **public API surface**：
  - `node_store.set_forward_host(node_id, forward_host)` / `node_store.get_forward_host(node_id) -> str | None`（platform 侧）。
  - `NodeStatusBody` 新增可选 `forward_host: str | None = None`（node→platform 心跳契约）。
  - `node.config.NodeConfig` 新增 `advertise_host: str | None`。
  - `agent_transport` 内部地址解析（优先用 `node_store` 持久化地址，回落 `forwarder_contract`）。`forwarder_contract.py` 纯函数签名不变，继续作兜底。
- **owned tables**：`nodes`（管理库，MODIFY：加 `forward_host` 列）——仅由 Alembic 维护。
- **config namespace**：新增**可选**环境变量 `FLEETENT_NODE_ADVERTISE_HOST`（node 侧）；既有 `FLEETENT_FORWARDER_HOST_OVERRIDE`（platform 侧）语义不变，降为优先级中段兜底。
- **cross-module dependencies**：node SHALL NOT `import fleetent.platform.*`（不变，node→platform 仅 HTTP）。转发寻址优先级置于 platform 侧 `agent_transport`，读 platform 自有的 `node_store`，不让 `node/` 包引入 DB 依赖。`agent_transport` 对 `node.forwarder_contract`（纯函数）的既有 import 保留作兜底。
- **migration / shim plan**：一条 Alembic 迁移给 `nodes` 加 `forward_host TEXT`（nullable，默认 NULL）。纯增量：旧 node（不上报 `forward_host`）该列保持 NULL → 寻址自动回落 override / `.internal`，零行为回归；新 node 上报后即生效。无需 shim。
- **范围外**：不改注册（`register_node`）流程与 `fleetent platform node register` CLI（地址走心跳而非注册，避免地址静态化、支持网络变更自愈）；不改转发端口/协议；不引入 platform→node 的服务发现/健康探活；不做地址多候选（一机一 node 单地址即可）。
