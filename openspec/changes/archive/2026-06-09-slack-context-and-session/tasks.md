## 1. Session 派生:thread-first、按 thread 根 key

- [x] 1.1 Write failing tests for `_derive_session_id`:DM 顶层=`slack:dm:{u}:{ts}`、DM thread 内同 key、assistant thread 各自独立、频道顶层=`slack:thread:{ch}:{ts}`、频道 thread 内同 key、DM 与频道不撞
- [x] 1.2 Implement `_derive_session_id` 新方案(入参含 channel_id/channel_type/thread_root),更新 assistant 路径与 `_handle` 调用(传 channel_id、真实 channel_type、thread_root=thread_ts or event_ts)
- [x] 1.3 Write failing test:thread-first 回复——顶层消息 reply 落进以其 ts 为根的 thread(mock say/assistant,断言 thread 根一致)
- [x] 1.4 Implement/verify thread-first 回复通过 1.3

## 2. NormalizedMessage.session_context 字段 + 适配器填充

- [x] 2.1 Write failing tests:`NormalizedMessage` 有 `session_context`(默认 None);Slack DM/频道填充正确字段(platform/sender_id/sender_name/chat_type/channel_name/was_mentioned/thread_root)
- [x] 2.2 Implement:加字段 + Slack 适配器(assistant 路径 + `_handle`)填充
- [x] 2.3 Write failing/verify:Telegram 适配器填充最小可用 session_context(platform/sender),不退化
- [x] 2.4 Implement/verify Telegram 通过 2.3

## 3. 上下文注入(system 框架 + user 前缀)

- [x] 3.1 Write failing tests:带 session_context 时,normalizer 把会话框架(platform/DM-or-频道/频道名/日期+时区)拼进 system_content、把发送人(id+名+是否@bot)拼进 user_content 前缀;不带时两者均不变
- [x] 3.2 Implement normalizer 双注入(时间函数可注入 now/tz)
- [x] 3.3 Write failing test:日期级时间(不含分钟),含时区

## 4. whoami 工具

- [x] 4.1 Write failing tests:`whoami` 返回当前发起人 sender_id/sender_name/platform/chat_type/channel_name+时间;无 session_context 时降级返回「未知」不抛异常
- [x] 4.2 Implement:把 session_context 透传到工具执行上下文;新增 `whoami` 内置工具读取之

## 5. 收尾验证

- [x] 5.1 受影响层:`uv run pytest tests/unit -q`(im_gateway/tools/runtime 相关,无新增失败)
- [x] 5.2 改动文件 ruff format/check + `uv run mypy src`
- [x] 5.3 架构:im_gateway/tools/runtime 不 import platform.*;agent 可脱离 platform 独立运行(无 session_context 时降级正常)
- [x] 5.4 PR 门禁:`make test-pr` 全绿(除预存在 path 失败);integration 相关子集无新增失败
