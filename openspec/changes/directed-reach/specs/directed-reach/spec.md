## ADDED Requirements

### Requirement: 按 user_id 的定向触达原语
系统 SHALL 提供按内部 `user_id` 主动触达用户的能力：agent 侧 `notify_user(user_id, message)` 产生一条 user_id-目标的出站意图，**不在 agent 进程解析渠道地址、不调用 platform**。地址反查与投递由 node 在 drain 时完成（node 经 node-key 调 platform 反向解析端点）。该能力 SHALL 复用既有 `im_outbound_queue` 出站脊柱，user_id-目标意图以 `address_json` 内的 `target_type="user_id"` 表达，不引入新表。

#### Scenario: agent 只发意图不碰地址
- **WHEN** agent 调 `notify_user(user_id, message)`（node-managed 运行时）
- **THEN** 一条 `target_type="user_id"` 的意图入 `im_outbound_queue`，agent 进程不查 `im_users`、不调用 platform 端点

#### Scenario: 非 managed 运行时降级
- **WHEN** 在非 node-managed 的 `agent run`（无 node、无 im_users 表）调 `notify_user`
- **THEN** 该调用 no-op 并记录日志，不抛错

### Requirement: 平台反向地址解析（node-key）
系统 SHALL 提供 `POST /nodes/{node_id}/identity/addresses`，以 node service key 认证，入参含 `user_id`，返回该用户在 `im_users` 中的全部 `(platform, platform_user_id)` 绑定。底层查询 SHALL 为 `im_users WHERE user_id=X`。该端点供 node 反查，agent SHALL NOT 直接调用。

#### Scenario: 返回用户全部绑定
- **WHEN** node 以 user_id 调 `/identity/addresses`，该用户在 im_users 有多条绑定
- **THEN** 返回其全部 `(platform, platform_user_id)`

#### Scenario: 无绑定返回空
- **WHEN** user_id 在 im_users 无任何绑定
- **THEN** 返回空地址列表

### Requirement: node fan-out 投递与不可达降级
node drain 到 user_id-目标意图时 SHALL 反查地址并向该用户**全部绑定渠道 fan-out 投递**（每渠道一次）。单渠道投递失败 SHALL 只记日志、不影响该用户其它渠道、不中断 drain。当反查返回空（用户未绑定任何渠道）时，系统 SHALL NOT 投递，只记录日志（上游待办项保持待处理），且 SHALL NOT 回退到其它 approver。

#### Scenario: 全发所有绑定渠道
- **WHEN** node drain 一条 user_id 意图，用户绑了 Slack 与 Telegram
- **THEN** 两个渠道各收到一次该消息

#### Scenario: 无绑定不投递只记日志
- **WHEN** user_id 无任何绑定
- **THEN** 不发任何渠道，记录日志，不报错、不回退他人

### Requirement: reflection user-memory 提案送本人（A4b）
reflection 生成的 user-memory 维护提案 SHALL 经 directed-reach 通知提案 owner（`proposal.user_id`）本人审批，消息含 `approve <id>` / `reject <id>` 指令。owner 的回复 SHALL 经既有入站身份解析与审批路由关联回该 `memory_proposal` 审批请求（不新建回复通路）。owner 不可达（无绑定）时该提案 SHALL 保持待审批。

#### Scenario: user-memory 提案送达本人
- **WHEN** reflection 生成一条 user-memory 维护提案、owner 已绑定渠道
- **THEN** owner 经其渠道收到含 approve/reject 指令的审批提示

#### Scenario: 本人回复关联回提案
- **WHEN** owner 回复 `approve <id>`
- **THEN** 经既有审批链关联到对应 memory_proposal 并按既有逻辑 apply

#### Scenario: 本人不可达提案保持待审批
- **WHEN** owner 未绑定任何渠道
- **THEN** 该提案保持 pending、记录日志，不回退给其它 approver
