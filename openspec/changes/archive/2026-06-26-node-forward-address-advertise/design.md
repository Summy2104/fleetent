## Context

托管转发链路：admin 在 chat console 发起 `POST /admin/agents/{name}/chat` → `server.py:598 managed_agent_chat` → `platform/node_management/agent_transport.py:DirectHttpAgentTransport.chat` 用 httpx 拨 `f"{forwarder_base_url(node_id)}/forward/agents/{agent}/chat"`（WS 走 `forwarder_ws_url`）。`forwarder_base_url`（`node/forwarder_contract.py:14`）= `http://{_forwarder_host(node_id)}:8786`，而 `_forwarder_host` = `FLEETENT_FORWARDER_HOST_OVERRIDE` 或 `{node_id}.internal`。

node 端：`node/config.py` 从环境装载 `NodeConfig`（`node_id` 来自 `FLEETENT_NODE_ID`）；`node/reconcile.py:_post_status` 周期性 `POST {platform}/nodes/{node_id}/status`，当前 payload 仅 `{"agents": [...]}`。platform 端 `node_desired_state_api.py:152 post_node_status` 收到后 `node_store.touch_last_seen(node_id)` + 逐 agent `upsert_agent_status`。

`nodes` 表（管理库，Alembic 维护）当前列：`id, name, key_hash, labels, registered_at, last_seen_at, created_at, updated_at`——**无地址列**。`node_store._COLS` 据此拼 SQL，`get_node` / `list_nodes` 返回这些列。

约束：node SHALL NOT `import fleetent.platform.*`；管理表仅由 Alembic 维护（不在 store `_init_db` 建表）。

## Goals / Non-Goals

**Goals:**
- platform 拨 node forwarder 不再依赖外部 DNS 解析 `{node_id}.internal`：node 自报可达地址、platform 持久化并优先使用。
- 跨服务器即插即用：新 node 配一个 `FLEETENT_NODE_ADVERTISE_HOST` 即可被 platform 正确转发；agent↔node 多对多多机天然支持（每 node 各自地址）。
- 零行为回归：未上报地址的旧 node 回落既有 override / `.internal` 约定。

**Non-Goals:**
- 不改注册流程/CLI（地址走心跳不走注册，支持网络变更自愈、避免静态化）。
- 不引入服务发现、健康探活、地址多候选。
- 不改转发端口（8786）与协议（http/ws）。

## Decisions

### 决策 1：地址走 status 心跳上报，不走注册

复用既有 `POST /nodes/{id}/status` 心跳通道捎带 `forward_host`，而非在 `register_node` 时静态登记。

**Why**：① 注册是一次性运维动作（`fleetent platform node register`），地址写死后机器换 IP 就失效；心跳每轮刷新 → 网络变更自愈。② 不改注册/CLI/`agent-node-registry` 注册相关 scenario，影响面最小。③ 心跳已是 node 周期主动联系 platform 的现成通道，零新增端点。

### 决策 2：`nodes` 表加 `forward_host` 列（Alembic，nullable）

`nodes` 新增 `forward_host TEXT`（nullable，默认 NULL）。`node_store._COLS` 加入该列；新增 `set_forward_host(node_id, forward_host)`（`UPDATE nodes SET forward_host=:fh, updated_at=:now WHERE id=:id`，named params）与 `get_forward_host(node_id) -> str | None`；`get_node` / `list_nodes` 自然带出该列。

status 端点 `post_node_status`：`body.forward_host` 非空时调 `node_store.set_forward_host(node_id, body.forward_host)`（紧邻既有 `touch_last_seen`）。`NodeStatusBody` 加 `forward_host: str | None = None`（缺省兼容旧 node）。

**Why**：管理表必须 Alembic（双权威）；nullable 默认 NULL 使存量 node 与未配置 node 自动回落，迁移零风险。

### 决策 3：转发寻址优先级置于 platform 侧 `agent_transport`，`node/` 不碰 DB

在 `agent_transport.py` 新增内部 host 解析：
```
resolved_host = node_store.get_forward_host(node_id) or None
base = (
    f"http://{resolved_host}:{PORT}" if resolved_host
    else forwarder_base_url(node_id)   # 既有：env override → {node_id}.internal
)
```
WS 同理（`ws://` / `forwarder_ws_url`）。`forwarder_contract.py` 纯函数签名与行为**不变**，继续承载「override → `.internal`」兜底两段。

**Why**：① 寻址优先级是 platform 出站策略，读 platform 自有 `node_store` 天经地义；放 platform 侧避免 `node/forwarder_contract`（被 node 进程 import）引入对管理库的依赖，守住「node 不依赖 platform/DB」。② `forwarder_contract` 保持纯函数 → 既有 node 侧用法（若有）和 override 语义不破坏，仅被"前置一段 DB 查询"包裹。③ 优先级 `DB → override → .internal`：已上报地址最权威；override 仍可作单机/测试强制兜底；`.internal` 兜底给"配了外部 DNS"的部署。

### 决策 4：node 端 `advertise_host` 为可选配置

`node/config.py:NodeConfig` 加 `advertise_host: str | None`，从 `FLEETENT_NODE_ADVERTISE_HOST` 读（未设为 None）。`reconcile._post_status` 仅当 `self._config.advertise_host` 非空时在 payload 加 `"forward_host"`。

**Why**：可选 → 不破坏未配置的现有部署（回落约定）；由部署者显式声明该机可达地址，比 platform 端从请求 source IP 推断更可靠（source IP 受 NAT/反代干扰，本案 platform↔node 同机但经 CF 入站，source IP 不可信）。

## Risks / Trade-offs

- **地址配错 → 转发到错误 host**：风险等同于今天配错 override，但范围收敛到单 node（仅该 node 的转发受影响），且日志会暴露 ConnectError 指向具体 host，可诊断。
- **心跳前的空窗**：node 重启后首次心跳前 `forward_host` 仍是上一次值（持久化），不会丢；全新 node 首次心跳前转发会回落 `.internal`（与现状一致，心跳秒级补齐）。
- **未上报的存量 node**：列为 NULL → 回落 override / `.internal`，与当前行为完全一致，无回归。

## Migration Plan

1. Alembic 迁移：`nodes` 加 `forward_host TEXT`（nullable）。`alembic upgrade head` 随 platform 启动/部署执行。
2. 代码上线后，已在跑的 node 下一轮心跳即上报地址（若已配 `FLEETENT_NODE_ADVERTISE_HOST`），platform 自动改用持久化地址。
3. 部署文档：每台 node 机的 node 环境配置加 `FLEETENT_NODE_ADVERTISE_HOST=<本机对 platform 可达地址>`（生产单机即 `127.0.0.1`）。

## Open Questions

- 是否需要在 admin node 列表 UI / API 展示 `forward_host` 以便运维核对？（倾向：后续增量，本 change 仅做数据面打通，不阻塞。）
