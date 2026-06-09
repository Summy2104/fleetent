## Context

`im-progress-feedback` 现有实现:`im_gateway/slack.py` 在 `_handle()` 里裸调 `client.assistant_threads_setStatus(...)`,`thread_ts` 取 `event.get("thread_ts") or event.get("ts")`;`runtime/loop.py` 的 `_plan_run_slots()` 在**规划阶段**逐个工具发出 `progress_func({"type":"tool_call","name":...})`,随后 `tool-parallel-dispatch` 用 `asyncio.gather` **并行**执行整批。

运行时插桩证实:fleetent 的 setStatus 调用全部成功、文案正确(`🤔 思考中` / `📅 正在查询日历` / `📂 正在操作 Google Drive`),但用户在 Assistant 面板看到的是 Slack 默认 loading 轮播。Slack 官方文档说明:Assistant app 必须监听 `assistant_thread_started` 获取 assistant 线程的 `channel_id`+`thread_ts`,并以该 `thread_ts` 调 `assistant.threads.setStatus`;推荐用 slack-bolt 的 `Assistant` 容器统一处理。fleetent 用消息自身 ts 当 `thread_ts`,状态落在非面板线程,面板遂回退显示 Slack 默认值。

约束:本改动全部位于 agent runtime(`im_gateway/`、`runtime/`),不得 `import fleetent.platform.*`、不得写 platform 表;agent 必须仍能脱离 platform 独立运行。

## Goals / Non-Goals

**Goals:**
- Slack bot 设置的 per-tool 状态真正渲染到用户所在的 Assistant 面板(绑定正确的 assistant `thread_ts`)。
- 一轮多个并行工具时,进度体现该轮**全部**在途工具,而非只剩最后一个。
- 未启用 Agents & Assistants 的 App 平滑降级为纯 `say()`。
- Telegram 现有 typing 行为不退化。

**Non-Goals:**
- 不改 `tool-parallel-dispatch` 的并行执行语义、回填顺序、取消传播。
- 不给 Telegram 增加 per-tool 文本状态(无原生 assistant 状态 API)。
- 不引入 suggested prompts / thread title 等 Assistant 附加能力(可后续单独提)。
- 不改 channel `app_mention` 在频道里的现有行为。

## Decisions

### D1: 采用 slack-bolt `Assistant` 容器处理 assistant 线程
用 slack-bolt(>=1.28)的 `Assistant` 中间件注册 `thread_started` 与 `user_message` 处理器。`user_message` 处理器从框架获得**已绑定到正确 assistant 线程**的 `set_status` / `say` / `context`,据此构造 `reply_func`(清状态 + say)与 `progress_func`(更新状态),再走 `route()`。这样彻底消除手工推导 `thread_ts` 的错误源。
- *备选*:手动监听 `assistant_thread_started` 缓存 `{channel→thread_ts}`,设状态时查缓存。否决:线程生命周期与并发边界需自管,非官方惯用法(脑暴已定全面采用 Assistant 类)。

### D2: 保留非 assistant 路径的回退
`Assistant` 容器只覆盖 assistant 面板/DM 会话。SHALL 保留:① channel `app_mention` 处理器(频道场景,无状态指示器或降级);② 当 App 未启用 Agents & Assistants 致 `set_status` 失败时,降级为纯 `say()`(与现状一致)。确保「无 assistant 功能」时 DM 仍能正常对话。

### D3: 多工具进度按「批次聚合」表示(解决并行下只剩一个)
关键认识:工具是**并行**执行的,「把发出时机从规划移到执行」单独并不能解决——并行批次里仍无单一「当前工具」。因此改为:`loop.py` 在**整批工具开始执行时**发出**一次**批级进度事件,携带该批**全部**工具名;Slack 适配器据此渲染**聚合**状态(如「📅 正在查询日历 · 📂 正在操作 Google Drive…」)。
- 进度事件契约调整:`{"type":"tool_call","names":[...]}`(N=1 即单元素列表)。为兼容现有消费者保留 `"name"=names[0]`。
- guardrail 判定与风险审批 MUST 仍按原 `tool_calls` 顺序串行(不变);仅进度发出移到执行起点且聚合。
- sub_agent 内工具仍不触发父 `progress_func`(不变)。
- *备选*:用 `set_status` 的 `loading_messages` 数组让 Slack 自行轮播工具名。否决:轮播是定时的,与真实完成解耦,不如聚合如实;且把表示逻辑交给 Slack 端不可控。

### D4: 适配器消费聚合事件
- Slack:`progress_func` 收到 `names` 列表 → 映射每个工具为可读文案 → 合成一条聚合状态串调 `set_status`。
- Telegram:收到事件即发 `sendChatAction("typing")`,忽略 `names`(行为不退化)。

## Risks / Trade-offs

- [Slack App 未启用 Agents & Assistants 功能] → `thread_started`/`user_message` 不会触发、`set_status` 失败。Mitigation:D2 的回退路径保证 DM 仍可用;部署侧需在 api.slack.com 启用该功能并授予 `assistant:write` scope(见 Migration)。
- [`Assistant` 容器与现有 `@app.event("message")` DM 处理器职责重叠/冲突] → 双重响应。Mitigation:assistant 路径接管 DM 后,移除/收敛原 `message`(im)处理器,仅保留 `app_mention`;单测覆盖「DM 只被响应一次」。
- [进度事件契约从 `name` 改为 `names`] → 现有消费者(telegram、潜在测试)。Mitigation:保留 `name=names[0]` 向后兼容;telegram 不读 names。
- [聚合状态串过长(一轮工具很多)] → 状态文案超限。Mitigation:超过阈值时截断为「前 N 个 + …等 k 项」。

## Migration Plan

- 纯代码改动,无数据迁移、无 schema 变更。
- **部署前提(配置侧,非本仓代码)**:Slack App 需启用 *Agents & AI Apps* 功能并具备 `assistant:write` scope,assistant 面板状态才会渲染;未启用时按 D2 降级,不阻断对话。
- 回滚:还原 `slack.py`/`loop.py` 即可,无残留状态。

## Open Questions

- 聚合状态串的具体格式与截断阈值(实现时定,属表现细节,不影响 spec 行为)。
