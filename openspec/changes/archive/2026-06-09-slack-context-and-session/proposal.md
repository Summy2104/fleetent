## Why

两个相关缺口:

1. **LLM 拿不到发起人/渠道/时间**:Slack 消息进来后,fleetent 把 Slack user ID 用于 session/记忆/鉴权,但**从不注入给 LLM**(实测 my-bot 无法说出发起人 Slack ID,只能从文本瞎猜)。agent 因此不知道"谁、在哪、何时",无法做身份相关应答、@人、时效判断。

2. **session 隔离不合理**:`_derive_session_id` 现状——DM 与频道顶层 @mention 都落 `user:{id}`(撞 key,DM 与频道历史混在一起);助手面板「新对话」不开新 session(thread_ts 被忽略,历史一直沿用);频道顶层 @mention 与其后续 thread 追问 key 不一致(对话被劈成两段)。

## What Changes

**Part A — 上下文注入(im-message-context,新能力)**
- 适配器把发起人/渠道元数据填进 `NormalizedMessage.session_context`(平台可信项:platform、sender_id、chat_type、channel_name、was_mentioned;用户项:sender_display_name)。
- **混合注入**:会话框架(platform、DM/频道、频道名、当前日期+时区)注入 **system 段**;本条发送人(Slack ID + 名 + 是否 @bot)注入 **user 消息前缀**。
- 新增 **`whoami` 内置工具**:按需返回发起人 Slack ID / 名 / 渠道 / 当前时间。

**Part B — session 隔离 + thread-first(modified im-gateway)**
- **thread-first**:bot 收到顶层消息即在该消息上开 thread 回复;thread 内追问继续同一 thread。
- **session key 按 thread 根**(`thread_root = thread_ts or event_ts`):
  - DM → `slack:dm:{user}:{thread_root}`
  - 频道 → `slack:thread:{channel}:{thread_root}`
- 效果:DM/频道规则统一;助手面板新对话天然开新 session;顶层消息与其 thread 内追问同 key、不再劈裂;DM 与频道因命名空间天然分开。

## Capabilities

### New Capabilities
- `im-message-context`: 把发起人身份、渠道/场景、时间注入 LLM(system 段 + user 前缀),并提供 whoami 工具按需取。

### Modified Capabilities
- `im-gateway`: session_id 派生改为 thread-first、按 thread 根 key 的方案;`NormalizedMessage` 新增可选 `session_context` 字段。

## Impact

- **代码**:`im_gateway/slack.py`(session 派生、thread-first 回复、填 session_context)、`im_gateway/normalizer.py`(双注入)、`im_gateway/telegram.py`(填 session_context,可空)、`tools/`(whoami 内置工具 + 把 session_context 透传到工具上下文)、`agent_config`/run() 视需要。
- **迁移影响**:session key 方案变更,**现有旧 session 历史断档**(新 key 找不到旧 `user:{id}`/`thread:{ts}` 历史)——对话历史而已,切换可接受,proposal 写明。
- **测试**:slack/telegram session 派生与 session_context 填充、normalizer 双注入、whoami 工具、thread-first 回复。
- **架构**:全部在 agent runtime(im_gateway/tools/runtime),不依赖 platform。
