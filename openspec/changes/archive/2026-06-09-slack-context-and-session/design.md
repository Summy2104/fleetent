## Context

现状:`_derive_session_id`(slack.py)对 DM 和频道顶层 @mention 都返回 `user:{id}`(撞 key);助手路径硬编码 `channel_type="im"` 忽略 thread_ts(新对话不开新 session)。`run()`/normalizer 从不把发起人/渠道/时间注入 LLM。本设计在不破坏 agent/platform 解耦的前提下补这两块。

## Goals / Non-Goals

**Goals:**
- LLM 能获知发起人(Slack ID + 名)、渠道/场景(platform、DM/频道、频道名、是否@bot)、当前日期+时区;并提供 whoami 工具按需取。
- session 派生 thread-first、按 thread 根 key,DM/频道统一、无劈裂、互不撞 key、助手面板新对话开新 session。

**Non-Goals:**
- 不引入 untrusted 标注(按用户决定,直接注入)。
- 不改记忆/鉴权按 user_id 的归属。
- 不改频道 thread「串内共享」语义(仍多人共享一个 thread session)。
- 不做旧 session 历史迁移(切换断档可接受)。

## Decisions

### D1: session 派生 thread-first、按 thread 根
`thread_root = thread_ts or event_ts`(bot 回复落进的 thread 根)。
- DM(im)→ `slack:dm:{user_id}:{thread_root}`
- 频道 → `slack:thread:{channel_id}:{thread_root}`
顶层消息(无 thread_ts)用自己的 ts 当 thread_root,与其后续 thread 内追问(thread_ts=该 ts)落同一 key,对话连续。助手面板每段 assistant thread 各自 thread_ts → 新对话开新 session。
- *备选*:频道顶层按 user(`channel:{ch}:{user}`)。否决:与其自动创建的 thread(shared)key 不一致,导致同段对话劈裂(评审中发现)。

### D2: thread-first 回复
bot 回复用 `thread_ts = thread_root` 落进该 thread(顶层消息即在其上开 thread)。fallback 路径已是 `say(thread_ts=reply_thread)`;assistant 面板对话本身即 assistant thread。统一保证「回复所在 thread == session 的 thread 根」。

### D3: 上下文注入(混合,不标 untrusted)
- 适配器填 `NormalizedMessage.session_context`(dataclass):`platform`、`sender_id`、`sender_name`、`chat_type`(dm/channel)、`channel_name`、`was_mentioned`、`thread_root`。
- **system 段**(normalizer 拼进 system_content):会话框架——platform、DM/频道(+频道名)、当前日期+时区。
- **user 前缀**(normalizer 拼进 user_content 前):本条发送人——`sender_id` + `sender_name` + 是否@bot。一行紧凑,不标 untrusted。
- 时间:由注入侧统一取当前日期(date 级,保缓存)+ 时区(取 agent 配置/系统,缺省合理值);函数可注入 now/tz 以便测试。

### D4: whoami 内置工具
新增 `@tool whoami`,返回当前发起人 `sender_id`/`sender_name`/`platform`/`chat_type`/`channel_name`/当前时间。需把 `session_context` 透传到工具执行上下文(沿现有 tool_context/ user_id 透传链扩展一个可选字段),工具从中读取。不可用时返回「未知」。

## Risks / Trade-offs

- [旧 session 历史断档] → 切换后旧 `user:{id}` 历史不再被命中。Mitigation:仅影响对话历史连续性,长期记忆按 user_id 不受影响;proposal 写明,可接受。
- [user 前缀进历史,长会话累积] → 保持一行紧凑;可接受。
- [whoami 需把 context 透传到工具层] → 沿现有透传链加可选字段,不可用时降级;避免大改 dispatch。
- [不标 untrusted 的注入安全] → 用户显式选择;平台可信项(Slack ID/channel)本就可信,sender_name 风险由用户接受。
