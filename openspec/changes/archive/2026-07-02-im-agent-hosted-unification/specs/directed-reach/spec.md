## MODIFIED Requirements

### Requirement: 按 user_id 的定向触达原语
系统 SHALL 提供按内部 `user_id` 主动触达用户的能力：agent 侧 `notify_user(user_id, message)` 在 node-managed 运行时 SHALL **在 agent 进程内**经 node loopback 反查该 user_id 的渠道地址，并用 agent 自持的活连接器投递。agent SHALL NOT 直接 import platform、SHALL NOT 直读 `im_users`、SHALL NOT 持有 node service key（loopback 以 agent 的 `FLEETENT_TUI_TOKEN` 鉴权，node 侧补 service key 转发 platform）。该能力 SHALL NOT 依赖 `im_outbound_queue` 或 node 出站 drain（二者已移除）。

#### Scenario: agent 经 loopback 反查并自投
- **WHEN** agent 调 `notify_user(user_id, message)`（node-managed 运行时）
- **THEN** agent 经 node loopback 反查该 user_id 的绑定地址，并用自持活连接器投递；agent 进程不直读 `im_users`、不直调 platform、不入任何出站队列

#### Scenario: 非 managed 运行时降级
- **WHEN** 在非 node-managed 的 `agent run`（无 loopback、无 im_users 表）调 `notify_user`
- **THEN** 该调用 no-op 并记录日志，不抛错

### Requirement: 平台反向地址解析
系统 SHALL 提供平台侧反向地址解析：入参含 `user_id`，返回该用户在 `im_users` 中的全部 `(platform, platform_user_id)` 绑定，底层查询 SHALL 为 `im_users WHERE user_id=X`。该解析 SHALL 可经两条通道到达 platform：既有 `POST /nodes/{node_id}/identity/addresses`（node service key 鉴权，node 内部使用），以及 **node loopback `POST /agent/{name}/identity/addresses`**（agent 以 `FLEETENT_TUI_TOKEN` 鉴权调 node，node 补 service key 转发到 platform 端点）。两条通道的解析语义 SHALL 完全一致。

#### Scenario: 返回用户全部绑定
- **WHEN** 以 user_id 调地址反查，该用户在 im_users 有多条绑定
- **THEN** 返回其全部 `(platform, platform_user_id)`

#### Scenario: agent 经 loopback 反查
- **WHEN** managed agent 经 node loopback `/agent/{name}/identity/addresses`（TUI token）反查
- **THEN** node 补 service key 转发 platform，返回与 node 直调 `/nodes/{id}/identity/addresses` 相同的地址集

#### Scenario: 无绑定返回空
- **WHEN** user_id 在 im_users 无任何绑定
- **THEN** 返回空地址列表

### Requirement: fan-out 投递与不可达降级
反查到 user_id 的地址后，SHALL 向该用户**全部绑定渠道 fan-out 投递**（每渠道一次），投递方为 **agent 自持的活连接器**（不再经 node drain）。单渠道投递失败 SHALL 只记日志、不影响该用户其它渠道、不中断本次触达。当反查返回空（用户未绑定任何渠道）时，系统 SHALL NOT 投递，只记录日志（上游待办项保持待处理），且 SHALL NOT 回退到其它 approver。

#### Scenario: 全发所有绑定渠道
- **WHEN** agent 触达一条 user_id 意图，用户绑了 Slack 与 Telegram
- **THEN** 两个渠道各收到一次该消息（经 agent 活连接器）

#### Scenario: 无绑定不投递只记日志
- **WHEN** user_id 无任何绑定
- **THEN** 不发任何渠道，记录日志，不报错、不回退他人
