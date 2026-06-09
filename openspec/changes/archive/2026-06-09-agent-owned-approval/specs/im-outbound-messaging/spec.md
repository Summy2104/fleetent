## ADDED Requirements

### Requirement: agent 可向指定目标主动发送消息
im_gateway **MUST** 提供能力，让 agent **主动**向指定的用户或频道发起消息，与任何入站事件无关。Slack 必须开启/复用与某工作区用户的私信频道（`chat_postMessage`）；Telegram 必须向指定 chat id 发送（`send_message`）。

#### Scenario: 向 Slack 工作区用户私信
- **WHEN** agent 请求向某 Slack user id 发送文本
- **THEN** 网关与该用户开启 DM 频道，并经 `chat_postMessage` 投递该文本

#### Scenario: 向 Telegram chat id 发送
- **WHEN** agent 请求向某 Telegram chat id 发送文本
- **THEN** 网关经 `send_message` 把文本投递到该 chat

#### Scenario: 出站独立于任何触发会话
- **WHEN** agent 向一个在当前 run 上下文中没有任何入站消息的目标发送
- **THEN** 投递仍然发生（发送不依赖回复线程/触发事件）

### Requirement: 各平台可达性必须可校验
该能力 **MUST** 在发送前/发送时暴露目标在其平台上是否可达，编码各平台约束，使调用方能确定性地兜底，而非以不透明方式失败。

#### Scenario: 从未 /start 过 bot 的 Telegram 用户
- **WHEN** 出站发送目标是一个从未 `/start` 过 bot 的 Telegram 用户（无已知 chat id）
- **THEN** 该目标被报告为不可达，且发送不会静默成功

#### Scenario: Slack 工作区用户可经 DM 触达
- **WHEN** 出站发送目标是已连接 Slack 工作区中的任意用户
- **THEN** 该目标可达，DM 被投递

### Requirement: 出站发送必须留在 agent 运行时边界内
出站能力 **MUST** 位于 `im_gateway`（agent 运行时），且**不得** `import fleetent.platform.*`；**MUST** 能在单机 agent（无 platform）下工作。

#### Scenario: 单机 agent 发送出站消息
- **WHEN** 一个单机 `fleetent agent run`（无 platform）在已配置的连接器上触发出站发送
- **THEN** 消息被投递，全程不经任何 platform 模块或管理库
