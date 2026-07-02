## Why

IM 交付的不确定性/不稳定性（症状：AAA-8208 脚本产物无法交付、AAA-8253 审批结果落点、AAA-8262 批准后无产出）的**根因是 standalone 与 managed 走了两条不同的 IM 路径**：standalone 下 agent 自持活连接器、直接收发；managed 下 node 持连接、agent 经"队列代理 → node drain"间接收发，且 managed 侧用**两套互相矛盾的"我是否 managed"信号**（OAuth 用已投递的 `FLEETENT_NODE_LOOPBACK_URL`，出站 `is_node_managed_runtime()` 却用**从未写入容器 agent `.env`** 的 `FLEETENT_NODE_ID/PLATFORM_URL/SERVICE_KEY`），失败还静默返回 `{}`。容器部署下该三件套恒缺 → `resolve_for_runtime` 返回空 → `send_file` 无连接器 → 交付无声失败。只要两条路并存，就会不断产生此类症状——**分叉本身就是不确定性的来源**。

## What Changes

- **统一为单一路径**：agent 全模式（standalone + managed）自持 IM 连接，复用 standalone 久经考验的直路收发。**BREAKING**（部署拓扑变更，未上生产、全量切、不灰度、不留 shim）。
- **node 退出 IM 数据面**：移除 node 的 Slack/Telegram supervisor、`/im/route` 入站端点、出站 drain、`im_outbound_queue`、`ManagedOutboundConnector`；`backend.spawn` 去掉 `--no-im`。node 仅保留 **identity/address 的 loopback 代理** + 进程监督。
- **agent 自持接线**：`agent_app.boot` 在 managed 下启动自己的 supervisor（token 已由 node materialize 写入 agent `.env`）；注入 `AgentIdentityResolver`/`AgentAddressResolver`（经 node loopback，agent 用 TUI token、不持 service_key）；supervisor 把活连接器注入 `NormalizedMessage.outbound_connectors`；回复/`send_file`/审批走活连接器直发；`notify_user`(directed-reach) 改为本地经 loopback 反查 `user_id→地址` + fan-out。
- **node loopback 身份端点**：`node/forwarder.py` 新增 `POST /agent/{name}/identity/resolve|addresses`（复用 `_forward_oauth` 范式）。
- **硬化**：统一 managed 判定为已投递的 `FLEETENT_NODE_LOOPBACK_URL`（废弃三件套判定）；`resolve_for_runtime` 在"managed 却无连接器"时 **fail-fast 记 error，不静默 `{}`**；`send_file` 无连接器文案带诊断。
- **契约锁定**：新增契约测试断言 **managed 行为 == standalone**（收发 / `send_file` / 审批往返 / directed-reach fan-out），防分叉复活。

## Capabilities

### New Capabilities
- `agent-hosted-im`: agent 全模式自持 IM 连接的统一运行模型——managed 下 agent 启动自身 supervisor、活连接器直发；node 退出 IM 数据面（移除 supervisor / `/im/route` / 出站 drain / 队列），仅保留 identity/address loopback 代理 + 进程监督；单一 managed 判定信号；`resolve_for_runtime` fail-fast 语义；`managed==standalone` 行为契约。

### Modified Capabilities
- `directed-reach`: `notify_user` 的地址反查 + 投递从"agent 入队 → node drain 反查 fan-out"改为"agent 经 node loopback 反查 + agent 活连接器 fan-out"；移除 `im_outbound_queue`/drain 依赖。
- `im-user-mapping`: 身份/地址解析新增经 **agent→node loopback**（TUI token 鉴权）调用的路径，与既有 node→platform 端点同源。

## Impact

- **owning packages**：`im_gateway/`、`node/`、`runtime/`、`outbound_connectors.py`
- **public API surface**：`im_gateway.access.AgentIdentityResolver` / `AgentAddressResolver` + `set_im_identity_resolver`/`set_im_address_resolver`；`node/forwarder` 的 `/agent/{name}/identity/resolve|addresses`；统一 managed 判定 helper（如 `runtime_placement.is_managed()`）
- **removed**：`node/im_edge` 的 supervisor+drain、`runtime/agent_app` 的 `/im/route` 入站端点、`im_outbound_queue`（`im_gateway/outbound_queue_store`）、`outbound_connectors.ManagedOutboundConnector`、`--no-im` 强制传参
- **owned tables**：移除 `im_outbound_queue`（迁移：全量切、无存量生产数据；升级脚本 drop 该表）
- **config namespace**：`agent.yaml im.*` 不变；**不新增** `im_host` 开关（全量切）
- **cross-module deps**：`im_gateway`/`runtime` → node/platform **仅 HTTP loopback 契约**，MUST NOT `import fleetent.platform.*`（护栏 `test_module_dependency_guardrails` 须保持绿）
- **migration/shim plan**：全量切、不留 shim；`/im/route`、队列、`ManagedOutboundConnector` 直接移除；旧路径代码删除前经契约测试确认新路径等价
- **关键约束**：Slack Socket Mode 每 `app_token` 独占一条连接、Telegram 每 `bot_token` 单轮询光标 → node 与 agent 不可同时持接收连接；本方案 node 彻底不持 IM 连接以规避。发送走 Web API，与 Socket 接收解耦。
