# platform-agent-gateway Specification

## Purpose
TBD - canonical spec structure repaired during archive of im-edge-on-node-outbound.
## Requirements
### Requirement: Node hosts the IM edge for its placed agents

在 managed 拓扑下，**node**（而非 agent 进程）SHALL 为其放置的 agent 持有 IM 连接（Slack Socket Mode 出站 WS / Telegram 出站 poll）并运行 IM-edge（adapter + supervisor）。agent 进程 SHALL NOT 再启动这些 IM 连接。连接生命周期 SHALL 与 agent 生命周期对齐（node 起某 agent 时一并开它的 IM 连接、停时关），每连接遵循既有 owner-task 契约。`im_gateway` 模块 SHALL 仍不 `import fleetent.platform.*`（身份解析经注入，见下）——它是换了执行宿主（agent→node）与注入方的 **edge face**。

standalone（无 platform）部署下，IM SHALL 仍可在 agent 进程内运行（resolver 未注入→退化），不破坏 `fleetent agent run` 基线。

#### Scenario: 托管下 node 持 IM 连接

- **WHEN** node 启动一个放置于其上、配置了 IM 的 agent
- **THEN** node 为该 agent 建立 Slack/Telegram 连接；agent 进程不建立 IM 连接

#### Scenario: standalone 下 agent 仍可跑 IM

- **WHEN** 无 platform 的 standalone 运行
- **THEN** IM 仍可在 agent 进程内工作（身份退化为原始 platform_user_id），`fleetent agent run` 不受影响

### Requirement: Platform identity-resolution endpoint for nodes

平台 SHALL 暴露一个 node 专用的身份解析端点（如 `POST /nodes/{node_id}/identity/resolve`），用 **node service key** 鉴权（既有 node→platform 通道），入参为渠道身份（platform、platform_user_id、可选 verified_email、tenant），调 `resolve_or_provision` 返回已解析的 `Principal`。node 注入一个**调用该端点**的 IM 身份 resolver；`im_gateway` 因此无需 import platform。

#### Scenario: node 经平台端点解析 IM 身份

- **WHEN** node 的 IM-edge 收到一条入站消息，调 `POST /nodes/{id}/identity/resolve`（带 node key）
- **THEN** 平台用 `resolve_or_provision` 解析/并号，返回 `Principal{user_id, tenant_id}`

#### Scenario: 未鉴权的解析调用被拒

- **WHEN** 无有效 node service key 调该端点
- **THEN** 平台拒绝（401/403），不解析

### Requirement: Node forwards resolved IM inbound to the local agent; sync reply returns via node

node IM-edge 解析出 Principal 后 SHALL 把 `{Principal, IM 入站}` 转给**本机 agent** 的 normalizer 入站（沿用 Principal-carrying 入站契约）；agent 跑 normalizer→loop、按该 Principal 归属本回合。本回合的**同步回复** SHALL 作为该转发的响应**返回给 node**，由持连接的 node 发回 IM——agent **MUST NOT** 依赖进程内 IM connector 直发同步回复。（异步/带外出站不在本要求，另行处理。）

#### Scenario: IM 入站经 node→agent→回复回发

- **WHEN** 用户经 Slack/Telegram 发消息
- **THEN** node 解析 Principal → 转给本机 agent normalizer → agent 跑 loop、按 Principal 归属 → 回复作为响应返回 node → node 发回 Slack/Telegram

#### Scenario: agent 不持连接也能回复同步消息

- **WHEN** agent 处理一条转发来的 IM 入站并产生回复
- **THEN** 回复经转发响应回到 node 发出，agent 全程不持 IM 连接、不直发

### Requirement: Node delivers agent async outbound via a delivery-queue

managed 下连接在 node、agent 进程无 live connector，因此 agent 的**异步/带外出站**（审批 DM、cron 触发外发、loop 内 send_im_message 等不经入站响应通道的出站）SHALL 经 **delivery-queue** 投递：agent 把出站意图写入本机 `agent_state.db` 的 `im_outbound_queue`（platform、conversation address、payload、dedup_key、status）；node 的 IM-edge SHALL 周期 **drain 本机队列**（读本地文件，非 RPC），经其持有的 connector 发出，再标记 sent。

投递 SHALL 为 **at-least-once + dedup**：node drain 用 `dedup_key` 防重发；发送失败的意图保留待重试（审批 DM 宁可能重发也不丢）。agent **只写自己侧队列、不持连接、不调 platform**；node **只读本机 agent 产物**——无 agent→platform。

standalone（连接在 agent 进程）下，异步出站 SHALL 维持现行进程内 connector 直发（不写队列），`fleetent agent run` 行为不变。

#### Scenario: managed 下审批 DM 经队列发出

- **WHEN** managed 下 permission_gate 要给审批人发 DM，但 agent 进程无 live connector
- **THEN** agent 把出站意图写 `im_outbound_queue` → node drain → 经其 connector 发给审批人

#### Scenario: node drain at-least-once + dedup

- **WHEN** node drain 队列发送，且发送后标记前 node 重启
- **THEN** 重启后该意图可能再次被取出，但凭 `dedup_key` 不重复发给用户（at-least-once 语义、dedup 兜重发）

#### Scenario: standalone 仍进程内直发

- **WHEN** 无平台/node 注入的 standalone 运行
- **THEN** 异步出站走进程内 connector 直发、不写队列，`fleetent agent run` IM 行为不变

#### Scenario: 出站不破解耦

- **WHEN** agent 产生任何异步出站
- **THEN** agent 只写本机 `im_outbound_queue`（自己侧产物）、不持连接、无对 platform 的调用；node 读本机队列发出

