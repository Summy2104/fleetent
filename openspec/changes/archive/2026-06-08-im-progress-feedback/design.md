## Context

normalizer.route() 当前调用 `agent_loop.run(messages=history, ...)` 返回最终字符串，
期间不产生任何进度信号。`run_stream()` 虽然已实现流式事件，但其签名接受
`user_input: str` 并自行组装 messages，与 normalizer 已维护完整 session history 的
做法不兼容——两者直接切换会导致 hook 重复执行、history 双重管理。

## Goals / Non-Goals

**Goals:**
- 用户发送消息后立即看到 bot 的响应迹象，而非等待沉默
- Slack：实时原地更新一条"思考中"占位消息，工具调用时展示工具名
- Telegram：定期触发 `sendChatAction("typing")`，利用平台原生打字指示器
- 工具名暴露：仅工具名，不含参数、输入内容

**Non-Goals:**
- 流式推送 LLM token（text_delta），仅进度指示，不做逐字打字机效果
- 全面切换 run_stream()（需重构 history 管理和 hook 链）
- 其他 IM 平台支持（未来可按相同 progress_func 接口扩展）

## Decisions

### D1：通过 progress_func 回调而非切换 run_stream()

`run_stream()` 接受 `user_input: str` 并内部组装 messages，而 normalizer
已加载 session history、执行多个 hooks（on_user_input、session_start）并将全量
messages 传给 `run()`。直接切换会导致 hook 重复执行和 history 双重管理。

**选择**：在 `agent_loop.run()` / `_run_inner()` 中新增
`progress_func: Callable[[dict], Awaitable[None]] | None` 参数，当工具调用开始时
以 `{"type": "tool_call", "name": "<tool_name>"}` 回调之。normalizer 从 `msg` 取
`progress_func` 并透传。

**放弃的替代**：新建 `run_from_messages_stream()` 以保持 messages-based + 流式兼容，
但工程量更大（需重构 `_run_inner` 为 AsyncGenerator），且当前只需工具名级别进度，
不需要全量 token 流，收益不匹配成本。

### D2：progress_func 挂载点在 tool dispatch 前（plan phase）

在 `_plan_run_slots()` 确定要执行哪个工具后、实际调度前（D5/D6 并发执行前），
以 `tool_call` 事件调用 `progress_func`。时机与 `run_stream()` 的 AR3/D8 三阶段
中 `tool_call` yield 对齐，确保用户在工具执行开始时立即看到提示。

### D3：Slack 消息更新节流 1 秒

Slack `chat.update` 频率上限约 1 次/秒（Tier 3: 50 RPM/channel）。
进度回调内部用 `asyncio` 时间戳判断距上次更新是否已超过 1 秒，未超过则跳过。
工具名取自事件 `name` 字段；占位文本格式：`🤔 思考中…` → `🔧 正在调用 <tool>…`。
最终回复由 `reply_func` 触发 `chat.update` 替换为完整内容。

### D4：Slack 使用 `client` 对象而非 `say()` 发起主动更新

`say()` 只能发新消息，无法更新已发消息。需要直接调用 `AsyncWebClient.chat_update()`，
token 从 `AsyncApp` 构造时传入的 `bot_token` 获取。
`handle_message` 中需接收 `client` 参数（slack-bolt 原生注入）。

### D5：Telegram typing action 在 progress_func 内调用 bot.send_chat_action()

Telegram 的"打字中"由 `python-telegram-bot` 的 `context.bot.send_chat_action(chat_id, "typing")`
触发，有效期约 5 秒。`progress_func` 每次被调用时重置该指示器。
无需持续轮询；工具调用间隔通常 > 1s，自然覆盖打字指示刷新窗口。

### D6：NormalizedMessage.progress_func 为可选，默认 None

不传则行为与当前完全一致（零改动）。所有现有测试无需改动。

## Risks / Trade-offs

- **Slack 占位消息的 `ts` 获取时机**：`say()` 在 `handle_message` 中是槽注入的，
  发送后返回值含 `ts`。需要改为 `await client.chat_postMessage(...)` 才能拿到返回值。
  → 测试时需 mock `client`，不能只 mock `say`。

- **progress_func 异常不能中断 run**：如 Slack API 调用失败，应 log 并忽略，
  不能 raise 给 `_run_inner`（否则破坏 agent run）。
  → progress_func 内部必须有 try/except。

- **`_run_inner` 扩散 progress_func**：内部调用链较深，需确保 progress_func
  只在 `_plan_run_slots` 调用，不扩散到 sub_agent 子调用。
  → sub_agent 不传递 progress_func，子 agent 的工具调用不产生进度事件。

- **Slack 初始消息在 session_lock 外发送**：占位消息应在 lock 前立即发送，
  然后再进入 `session_lock`。session_lock 持有期间不影响进度消息更新。

## Migration Plan

- 无数据库变更，无 Alembic migration
- `_run_inner` 新增 `progress_func: ... | None = None`（默认 None），向后兼容
- `NormalizedMessage` 新增 `progress_func` 字段（`field(default=None)`），向后兼容
- Slack / Telegram 适配器改动互相独立，可分别测试和上线
