## Context

fleetent 是 on-prem Lean Agent 平台,IM(Slack/Telegram)为主战场,另有单向 SSE `/chat` 和一次性 CLI。终端缺少交互式入口。调研三个参照系:

- **openclaw**(纯 TS,pi-tui 自研组件库,`TuiBackend` 接口抽象 embedded/gateway 两实现)——backend 抽象思想可借,渲染层是 TS-only,不可直接用。
- **hermes**(Python 后端 + Node/Ink 前端,`Transport` 协议三实现 + 单 dispatch + 双向 JSON-RPC,工程硬化高)——协议与 transport 设计是范本,但多一整个 Node/Ink 前端栈。
- **Aider**(纯 Python,`prompt_toolkit` 输入 + `rich` 输出,同进程行式渲染)——渲染栈范本,最轻、最贴合单栈。

现状可复用的拼图:`run_stream()`(async 事件源,yield `text_delta/tool_call/tool_result/done/error`)、`cancellation.CancelToken`、`permission_gate`(`asyncio.Event` 审批,已有 `/approvals` GET + resolve POST)、`session_mgr`(per-session `asyncio.Lock`)、`agent_store`、`user_store`(Bearer `ma-` key 认证)、FastAPI/starlette(自带 WebSocket)。新依赖候选 `prompt_toolkit`、`rich` 均不在 pyproject。

## Goals / Non-Goals

**Goals:**
- 终端交互式多轮聊天:流式渲染、多行输入、斜杠命令、历史。
- 运行中交互:中断(abort)、就地审批高风险工具(approve),走**同一双向通道**。
- 纯 Python 单栈、自托管、最少依赖;TUI 是 agent 服务的**客户端**,不嵌进 agent 进程。
- 协议 transport-无关(单 dispatch),为未来挂接其它传输留路。
- 全程可单测,不发真实 LLM/网络/docker。

**Non-Goals:**
- 不改现有 SSE `/chat`(保留并存)、`run_stream` 事件契约、工具注册/schema/访问控制、`permission_gate` 行为(仅消费/复用)。
- 不做 web/桌面/iOS/移动端客户端(只终端)。
- 不引入 Node/Ink/前端构建链;不引入 Textual。
- 不做 embedded 同进程模式(本 change 直接做 gateway WS 一步到位;embedded 留作未来可选)。
- 不做端到端真实集成测试(smoke 另算),单测一律 mock。

## Decisions

### D1 — 渲染栈用 `prompt_toolkit` + `rich`,拒绝 Textual/Ink

**选择**:新增依赖 `prompt_toolkit>=3.0.50`(输入)+ `rich>=14.0`(渲染)。

**理由**:
- 二者均**纯 Python、BSD/MIT、可自托管、无云服务、依赖极轻**(prompt_toolkit 仅 `wcwidth`/`Pygments`;rich 仅 `markdown-it-py`/`Pygments`),完全符合"基础设施可自托管 + 最少依赖"原则。
- **Aider 同款验证组合**:prompt_toolkit `PromptSession` 提供原生 async 多行输入 + `Completer`(斜杠命令补全)+ 历史 + 键绑定;rich 提供流式 Markdown、语法高亮、bordered panel(工具调用)、spinner(状态行)。覆盖全部需求。
- **async 集成原生**:`PromptSession.prompt_async()` 与既有 asyncio loop 协作(不自建 loop);`patch_stdout()` 让后台流式输出绘制在输入行之上、不串行。

**Alternatives**:
- **Textual**:全屏 reactive 框架,想当前台主进程、学习曲线陡、依赖更重;fleetent 终端只是辅助面(IM 为主),线性聊天 right-sized,Textual 杀鸡用牛刀。保留为"未来若演进成多面板 dashboard"的选项。
- **Ink/React**(Claude Code/Gemini CLI/hermes 前端):引入 Node 工具链 = 第二语言栈,直接违背单栈/最少依赖。**否决**。
- **rich 单用**:`rich.Prompt.ask` 是阻塞 `input()`,单行、无补全、无多行,输入能力不足。仅作渲染层。

### D2 — 协议:newline-delimited JSON-RPC 2.0,双向(借鉴 hermes)

**Wire**:每帧一行 `json.dumps(obj) + "\n"`;请求/响应/通知遵循 JSON-RPC 2.0。连接 accept 后服务端**立即发** `gateway.ready` 通知。

**客户端→服务端 方法(request,带 `id`)**:
- `send` `{message, session_id?}` → `{run_id}`:触发一次 agent run,事件经 `event` 通知流式回推。
- `abort` `{run_id}` → `{ok, aborted}`:中断指定 run。
- `approve` `{approval_id, decision}` → `{ok}`:`decision ∈ {approved, rejected}`,转 `permission_gate.resolve`。
- `session.new` `{}` → `{session_id}`;`session.list` `{}` → `{sessions:[...]}`(转 `session_mgr`)。

**服务端→客户端 通知(notification,无 `id`,`method: "event"`,`params: {type, payload, run_id?}`)**:
- `gateway.ready` `{}`;`text_delta` `{content}`;`tool_call` `{name, args}`;`tool_result` `{name, content}`;`done` `{content}`;`error` `{message}`;`approval_required` `{approval_id, tool, risk, args}`。
- 即:`run_stream` 的事件逐条映射为 `event` 通知;`permission_gate` 触发审批时推 `approval_required`。

**理由**:与 hermes 完全同构,wire 在不同 transport 上一致;newline-framed 易解析、易测。schema 锁进 `protocol.py` 常量 + spec。

### D3 — 用 WebSocket 而非沿用单向 SSE

**选择**:新增 `@app.websocket("/ws")`,**保留** `/chat` SSE 原样并存。

**理由**:TUI 的 `abort`/`approve`/`session.*` 是"客户端→服务端"的运行中交互,SSE 单向(服务端→客户端)无法在同一通道回传,只能靠侧 POST(状态分裂、配对易错)。WS 双向天然承载;FastAPI/starlette 自带 WebSocket,**零新依赖**。`/chat` SSE 服务于程序化集成,继续保留(Non-Goal 不改)。

### D4 — abort 传播复用 `cancellation.CancelToken`

`send` 启动 run 时创建 `CancelToken`,以 `run_id` 索引存于连接级状态;`abort` 查表 `cancel()`。`run_stream` 既有 cancel 接入会中断在途循环与工具(沙箱 `docker rm -f` 走既有 AR19 路径)。批次以 cancelled 收尾,不泄漏半截 tool-pair(依赖既有 message_hygiene/AR3 保序,不在本 change 重写)。`abort` 后服务端补发一条 `done`/`error`(state=aborted)通知让客户端收口。

### D5 — 审批流:`approval_required` 事件 + `approve` 方法

用户 `/approve` → 发 `approve{approval_id, decision}` → 网关转 `permission_gate.resolve(approval_id, decision, approver_user_id)` 放行/拒绝。**复用现有 `permission_gate` 与 `/approvals`,不改其行为**;WS 只是又一个 resolve 入口。

> **v1 范围修正(实施时发现)**:理想流程里 agent 触发 medium/high 工具时网关在事件流中推 `approval_required`、客户端渲染提示。但当前 `run_stream` 设 `include_approval=False`——**流式路径不做审批门控**(只有非流式 `run()` 门控),因此流式 run 不会产生 `approval_required`,网关也无从推送。本 change 不改 `run_stream` 契约(非目标),故 **v1 只实现 `approve`(解决)这一半**:它对任何来源的 approval 都能 resolve,与 `/approvals` 等价。让流式路径门控并发出 `approval_required` 是独立变更 **`streaming-approval-gating`**(给 `run_stream` 加可选 `include_approval` + yield approval 事件,同时影响 SSE `/chat`),落地后客户端审批渲染再启用。

### D6 — 认证:WS 握手校验 Bearer `ma-` key

WS 连接通过 `Authorization: Bearer ma-<hex>` header(或首帧 `hello{token}`,二选一,见 Open Questions)校验,复用现有 `user_store` 认证逻辑。校验失败 → 关闭连接(close code 1008/4401)。连接绑定到该 `user`,后续 `send`/`session.*` 在该 user 作用域内。

### D7 — loop/线程安全(借鉴 hermes WSTransport)

服务端:`WSTransport.write` 区分调用线程——事件循环线程内 fire-and-forget(`loop.create_task`,不阻塞自身);其它线程(若有池 worker)用 `run_coroutine_threadsafe + future.result(timeout)`。fleetent 的 `run_stream` 是 async 原生,主路径在 loop 线程,故以 fire-and-forget 为主;保留线程安全分支以防工具内有线程。客户端:`PromptSession.prompt_async()` 与 WS 接收协程并发跑在同一 loop,`patch_stdout()` 协调输出与输入行重绘。

### D8 — 多用户/会话隔离

每个 WS 连接持有独立连接状态(user、当前 session_id、`{run_id: CancelToken}` 表、transport)。session 经 `session_mgr`(per-session `asyncio.Lock`)访问,锁语义不变。不同连接/用户互不可见对方 run_id/session(`send` 默认作用在本连接绑定的 session;`session.list` 仅列该 user 的)。

### D9 — 错误与断连

- **peer-gone vs 真实错误**(借鉴 hermes transport):写帧时 `WebSocketDisconnect`/连接关闭 → 标记 transport 死、清理该连接的在途 run(cancel)+ session 解绑;真实 I/O/序列化错误 re-raise 进日志,不伪装成干净断开。
- **客户端**:连接失败/断开 → 显示状态行并按退避重连;startup/request 超时(可配置)。
- **解析错误**:非法 JSON 帧回 JSON-RPC `-32700`,不崩连接。

### D10 — 测试策略(TDD,全 mock)

- **网关/dispatch**:用 starlette `TestClient.websocket_connect` 驱动;`run_stream` 用 async generator stub(yield 预设事件序列);`permission_gate`/`session_mgr` monkeypatch 或注入;断言收到的 `event` 通知序列、`abort` 触发 cancel、`approve` 转 resolve、认证失败关闭码。
- **protocol/transport**:纯函数/小类单测——JSON-RPC 编解码、peer-gone 分类、WSTransport 用 fake ws 对象。
- **client 渲染/命令**:render 函数接收事件 → 断言 rich 输出(`Console(file=StringIO)` 捕获);斜杠命令解析纯函数单测;prompt_toolkit 用 `create_pipe_input` 注入按键。
- **路径常量可注入**(无全局可变状态);LLM/docker/网络一律不真实调用。

## Risks / Trade-offs

- [新增两个依赖] → 均纯 Python/自托管/Aider 验证,PR 说明必要性;锁定下限版本;不引入任何云服务或 Node。
- [WS 与 SSE 两套并存增加表面] → SSE 完全不改、互不影响;WS 仅新增,失败不影响既有路径。
- [prompt_toolkit + rich 同 loop 输出竞争] → `patch_stdout()` 是官方推荐解,Aider 已验证;client 侧单测覆盖渲染与输入并发。
- [abort 时半截 tool-pair] → 依赖既有 cancellation + message_hygiene + AR3 保序,不在本 change 重写;补发收口通知;测试覆盖 abort 后事件序列合法。
- [多连接共享 permission_gate 全局状态] → approval_id 唯一,resolve 幂等;WS 只是又一入口,与 `/approvals` HTTP 行为一致。
- [Textual 路线被排除可能限制未来富 UI] → 协议 transport-无关、渲染层隔离在 `tui/render.py`,未来换 Textual 仅替换渲染层,不动协议。

## Open Questions

- **认证位置**:WS `Authorization` header vs 首帧 `hello{token}`?倾向 header(与 `/chat` 一致、握手即拒);若部分客户端库不便设 WS header,则回退首帧。**实施时定,默认 header**。
- **入口形态**:独立 `fleetent-tui` script vs `fleetent tui` 子命令?倾向独立 script(`__main__.py` 当前是极简一次性,不宜塞子命令分发);**默认独立 script**。
- **WS 客户端库**:复用已有 `httpx`(其 WS 支持有限)还是新增 `websockets`?倾向新增 `websockets`(成熟、纯 Python、同 hermes),或用 starlette/`wsproto`。**实施时定,倾向 `websockets`,计入 D1 依赖论证**。
- **重连后状态恢复**:是否拉历史(`session.history`)?v1 可仅重连不补历史,后续增量。**默认 v1 不补历史**。
