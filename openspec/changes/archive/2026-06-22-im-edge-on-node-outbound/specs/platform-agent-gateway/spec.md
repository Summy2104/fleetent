## ADDED Requirements

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
