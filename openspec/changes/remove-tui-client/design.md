## Context

`fleetent` 的终端 TUI 由两层组成，**同一个 `tui/` 包**却服务两个不同角色：

```
fleetent-tui (客户端进程)                    agent daemon (fleetent agent run --port)
┌────────────────────────────┐              ┌───────────────────────────────────────┐
│ tui/app.py    REPL 主循环   │   WS /ws     │ agent_app.ws_gateway                    │
│ tui/backend.py 客户端连接   │ ───────────► │   import tui.dispatch  (Connection)     │
│ tui/commands.py slash 命令  │              │   import tui.protocol  (JSON-RPC codec) │
│ tui/render.py  终端渲染     │              │   import tui.transport (WSTransport)    │
└────────────────────────────┘              └───────────────────────────────────────┘
        纯客户端四件套                              服务端共用三件套（被 /ws 依赖）
```

关键事实（已核实）：
- `agent_app.py:641-643` 的 `/ws` 服务端处理器 import `tui.dispatch` / `tui.protocol` / `tui.transport`——这三个模块是 `/ws` 网关的**服务端协议实现**，并非客户端专属。
- 纯客户端四件套（`app`/`backend`/`commands`/`render`）在 `src/` 内**无任何非客户端导入者**，且保留三件套**不反向 import** 这四个模块。
- 多轮交互已由网页后台（`admin.html` + `chat_admin_api` 的 `/admin/chat/*`）独立覆盖，不经 `/ws`。
- `/ws` 全 src 唯一的客户端就是被删的 `fleetent-tui`；但 Randy 决定**保留 `/ws` 服务端**作为未来 WS 客户端/REPL 的传输入口。

## Goals / Non-Goals

**Goals:**
- 移除终端 TUI 客户端面（4 个客户端模块 + `fleetent-tui` 入口 + 客户端测试 + 安装脚本引用）。
- 完整保留 `/ws` 服务端栈：`/ws` 端点、`FLEETENT_TUI_TOKEN` 认证、`tui.dispatch/protocol/transport`、`/chat` SSE。
- 纯减法：删除后 `make test-pr` 与现有 `/ws` 服务端测试全绿，agent 仍能 `fleetent agent run`、网页后台聊天不受影响。

**Non-Goals:**
- 不补"Claude Code 式本地交互 REPL"（另起加法 change）。
- 不重命名/搬迁保留的 `tui/` 三件套（见 Risks 的延后项）。
- 不改 `/ws` 行为、不改 `agent_app.ws_gateway` 逻辑（仅其依赖的模块集合缩小，import 行不变）。
- 不碰 `data-model.md`、`openspec/specs/` 主 specs（delta 在 change 内）、不引入迁移。

## Decisions

1. **外科式删除，而非整包删除**：因 `/ws` 服务端依赖 `tui.dispatch/protocol/transport`，只删客户端四件套 `app`/`backend`/`commands`/`render`，保留三件套。这是"留 /ws"的直接推论。

2. **`fleetent-tui` 入口移除为 BREAKING**：`pyproject.toml` 删除该 console-script。运维迁移路径：网页后台聊天或 IM 渠道。安装脚本（`install*.sh`）同步去掉安装与"Connect TUI"提示。

3. **`FLEETENT_TUI_TOKEN` 保留**：它守 `/ws`，与客户端去留无关；`agent init` 仍写入 `.env`（`tui-agent-token-auth` 不变）。

4. **测试取舍**：
   - 删：`test_tui_app` / `test_tui_backend` / `test_tui_commands` / `test_tui_render`。
   - 部分编辑：`test_tui_logging` 移除 backend/app 用例，保留 transport/dispatch。
   - 保留不动：`test_tui_dispatch*` / `test_tui_protocol` / `test_tui_transport` / `test_tui_carries_principal`（import `tui.dispatch`，保留）/ `test_agent_runtime_ws` / `test_agent_app_tui_auth`。

5. **依赖收敛（apply 时核实后执行）**：`prompt_toolkit` / `rich`（仅 app/commands/render 用）、`websockets`（仅 backend 客户端用）若无其它使用者，从 `pyproject.toml` 移除；保留三件套依赖的 `starlette` 等不动。

6. **`tui/__init__.py` docstring 更新**：当前写"Interactive terminal TUI client"，删客户端后改述为"`/ws` 网关服务端协议/调度/传输（dispatch/protocol/transport）"。

## Risks / Trade-offs

- **保留的 `tui/` 命名名实不符**：删客户端后，`tui/` 仅剩服务端协议三件套，挂在名为 "tui" 的包下属误导。**延后项**：未来可把它们搬到 `runtime/ws_gateway/`（或类似），但那会触碰 `agent_app` import 与主 specs，属重构/加法，不在本减法 change 内。本 change 仅更新 `__init__.py` docstring 注明现状。
- **`/ws` 暂时零第一方客户端**：保留 `/ws` 但删掉唯一客户端，端点处于"有服务端、无随附客户端"状态。这是 Randy 的显式选择（留作未来 REPL/WS 客户端的传输入口）；服务端测试仍保证其行为可回归。
- **能力回退**：失去"从终端连到活的生产 daemon、共享其真实 session/IM 状态"这条路。评估为低痛——生产 agent 经 Slack/Telegram 与 `/chat` SSE 仍可对话，网页后台覆盖多轮交互。
- **依赖移除的连带风险**：移除 `prompt_toolkit`/`rich`/`websockets` 前必须全仓核实无其它 import，否则 apply 时会断其它模块；故列为"核实后执行"。
