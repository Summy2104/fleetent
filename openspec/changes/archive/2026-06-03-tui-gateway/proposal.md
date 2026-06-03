## Why

fleetent 目前只有一次性 CLI(`fleetent "<prompt>"`)和单向 SSE `/chat`,没有交互式终端界面:无法在终端里连续多轮对话、看流式输出、中断运行、就地审批高风险工具。运维/调试和"无 IM 时的直接使用"都缺一个像样的入口。本 change 新增一个**交互式终端聊天 TUI**,把它做成 agent 服务的又一个客户端——与已有的 IM 网关、SSE `/chat` 同属"前后端分离 + 协议"架构,而非把 UI 嵌进 agent 进程。

## What Changes

- **新增后端 WebSocket 网关 `/ws`**(FastAPI/starlette 自带,零新依赖):承载 **newline-delimited JSON-RPC 2.0 双向协议**。这是相对单向 SSE 的关键升级——`abort`/`approve` 等"客户端→服务端"的交互能在同一通道回传。
- **新增 Transport 抽象 + 单一 dispatch**(借鉴 hermes):`Transport` 协议(`write(obj) -> bool` / `close()`)与 `WSTransport` 实现;精确区分 peer-gone(客户端断开)与真实 I/O 错误;同一份 dispatch 处理所有方法,为未来挂接其它传输(stdio/web)留路。
- **新增纯 Python TUI 客户端 `src/fleetent/tui/`**:prompt_toolkit(async 多行输入 + 斜杠命令补全 + 历史)+ rich(流式 Markdown、工具调用面板、spinner 状态行)。连 `/ws`,消费 `event` 通知增量渲染;`patch_stdout` 让流式输出与输入行共存。斜杠命令 `/new /session /abort /approve /quit /help`;Ctrl-C → abort。
- **新增入口** `fleetent-tui`(`fleetent.tui.app:main`),`--url`/`--token` 连本地或远程 server。
- **新增依赖** `prompt_toolkit`、`rich`(均纯 Python、可自托管;论证见 design D1)。**明确禁止** Node/Ink/Textual。
- **复用**:Bearer `ma-` key 认证、`run_stream()` 事件源、`cancellation.CancelToken`、`permission_gate`、`session_mgr`、`agent_store`——均不修改其契约。

## Capabilities

### New Capabilities
- `tui-gateway`: 终端 TUI 与后端之间的契约——WebSocket `/ws` 上的双向 JSON-RPC 协议(连接握手与认证、`send`/`abort`/`approve`/`session.*` 方法、`event` 通知流)、Transport 抽象与 peer-gone 语义、每连接的用户/会话隔离,以及纯 Python TUI 客户端的渲染与交互行为(流式渲染、斜杠命令、审批与中断、断连处理)。

### Modified Capabilities
<!-- 无:本 change 只新增能力,不改任何现有 spec 的需求。/chat SSE、run_stream 事件契约、工具注册/访问控制、permission_gate 行为均保持不变(仅被消费/复用)。 -->

## Impact

- **代码(新增)**:`src/fleetent/tui/`(backend 抽象、transport、protocol、render、commands、app);`server.py` 新增 `@app.websocket("/ws")` 挂接 dispatch。
- **代码(复用,不改契约)**:`agent_loop.run_stream`、`cancellation`、`permission_gate`、`session_mgr`、`agent_store`、`user_store`(认证)。
- **依赖**:新增 `prompt_toolkit`、`rich`(纯 Python,自托管,无云服务);WebSocket 由现有 FastAPI/starlette 提供,无新增。
- **配置/入口**:`pyproject.toml` 新增 `fleetent-tui` script;新增可选 TUI 相关配置项(server URL/token 缺省、超时)。
- **不受影响**:现有 SSE `/chat`、`/health`、`/approvals`、`/webhook`、IM 网关、CLI 全部保持原样。
- **分支**:基于并合回 `main`(集成已完成,main 现为权威主干)。
