## Why

第一方终端 TUI（`fleetent-tui`）是一个纯 WebSocket 瘦客户端，挂到 agent daemon 的 `/ws` 上做多轮对话。它有三处冗余/尴尬：

1. **多轮交互已被网页后台覆盖**：admin 控制台（`admin.html` + `chat_admin_api` 的 `/admin/chat/*`）已提供完整的多轮对话、会话历史、agent 选择与流式输出，不依赖 `/ws`。
2. **它是"C 桶"运维客户端**：要先有一个 `fleetent agent run --port` 的 daemon 才能用，单独存在价值低（生产 agent 本就能经 Slack/Telegram 真实渠道与 `/chat` SSE 对话）。
3. **维护成本**：一个 prompt_toolkit/rich 终端 UI + 一批客户端单测 + 安装脚本入口，持续占用维护面。

本 change 做**纯减法**：移除终端 TUI 客户端，但**保留 `/ws` 服务端**（含 `FLEETENT_TUI_TOKEN` 认证），不引入替代物。"Claude Code 式本地交互 REPL"若需要，另起一个加法 change。

## What Changes

- **移除终端 TUI 客户端**：删除 `tui/` 包中**仅客户端**的模块 —— `app.py`（prompt_toolkit REPL）、`backend.py`（客户端 WS 连接）、`commands.py`（slash 命令）、`render.py`（终端渲染）。
- **移除 `fleetent-tui` console-script 入口**（`pyproject.toml`）。**BREAKING**：`fleetent-tui` 命令不再存在；运维需改用网页后台聊天或 IM 渠道。
- **保留 `/ws` 服务端栈**：`tui/dispatch.py`、`tui/protocol.py`、`tui/transport.py` 是 `/ws` 网关（`agent_app.py` 的 `ws_gateway`）**服务端共用**的协议/调度/传输实现，**继续保留**。`/ws` 端点、`FLEETENT_TUI_TOKEN` 认证、`/chat` SSE 均不变。
- **清理安装脚本**：`install.sh` / `install-platform.sh` / `install-agent.sh` 中安装与连接 `fleetent-tui` 的引用。
- **清理客户端单测**：删除 `test_tui_app/backend/commands/render`；部分编辑 `test_tui_logging`（移除 backend/app 用例，保留 transport/dispatch）。保留服务端测试（`test_tui_dispatch*`、`test_tui_protocol`、`test_tui_transport`、`test_tui_carries_principal`、`test_agent_runtime_ws`、`test_agent_app_tui_auth`）。
- **可选依赖收敛**：若 `prompt_toolkit` / `rich` / `websockets` 仅被被删客户端模块使用，从 `pyproject.toml` 依赖中移除（apply 时核实）。

不做：不补 REPL、不重命名保留的 `tui/` 模块（见 design 的延后项）、不动 `/ws` 行为、不动网页后台。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `agent-tui-logging`: 移除 `tui.backend` 与 `tui.app` 两条日志要求（对应模块被删）；保留 `tui.transport`、`tui.dispatch`（服务端共用模块仍在）。
- `install-bootstrap`: "Global command installation" 不再要求安装 `fleetent-tui`，仅 `fleetent` + `fleetent-admin`。

<!-- 不变：tui-gateway（/ws 服务端保留）、tui-agent-token-auth（FLEETENT_TUI_TOKEN + /ws 认证保留）、install-agent-script（仅要求 .env 含 token，保留）。 -->

## Impact

**owning package**：agent runtime（`src/fleetent/tui/` 客户端模块）+ 打包（`pyproject.toml`）+ 安装脚本（`scripts/install*.sh`）。`runtime/agent_app.py` 仅保留对 `tui.dispatch/protocol/transport` 的既有 import，**逻辑不变**。

**public API surface（移除）**：`fleetent.tui.app` / `.backend` / `.commands` / `.render` 模块；`fleetent-tui` console entry。
**public API surface（保留）**：`fleetent.tui.dispatch` / `.protocol` / `.transport`（被 `agent_app` 的 `/ws` 网关消费）。

**owned tables**：无（零 schema、零迁移）。

**config namespace**：`FLEETENT_TUI_URL`（客户端 env）随客户端移除而从文档/脚本清除；`FLEETENT_TUI_TOKEN` **保留**（继续守 `/ws`）。

**cross-module dependencies**：`runtime → tui.dispatch/protocol/transport` 不变；无新增依赖；不触碰 agent↔platform 边界（全程 agent runtime 侧）。保留三件套不反向 import 被删的客户端四件套（已核实）。

**migration / shim plan**：无持久层改动、无迁移。被删模块在 `src/` 内无导入者（仅被删的客户端测试 import），**无需 re-export shim**。

**受影响代码**：`src/fleetent/tui/{app,backend,commands,render}.py`、`tui/__init__.py`（docstring 更新）、`pyproject.toml`、`scripts/install*.sh`、`tests/unit/test_tui_{app,backend,commands,render,logging}.py`。
