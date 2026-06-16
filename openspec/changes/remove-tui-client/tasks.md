# Tasks

> 纯减法 change。TDD 在这里的形态：先用最窄命令确认"被删面已无引用 / 保留面仍绿"（红），再做删除（绿）。每个删除任务收尾跑受影响层，确保无新增失败。基线对照 main（门禁判据＝无新增失败）。

## 1. 前置核实（不改代码，定 scope）

- [ ] 1.1 全仓核实 `prompt_toolkit` / `rich` / `websockets` 的 import 者：`grep -rn "prompt_toolkit\|import rich\|from rich\|websockets" src/` —— 确认是否仅被 `tui/{app,backend,commands,render}.py` 使用，据此决定 task 5 是否移除这三个依赖
- [ ] 1.2 复核保留三件套（`tui/dispatch,protocol,transport`）在 `src/` 内的全部导入者，确认删客户端后无悬空 import：`grep -rn "fleetent.tui" src/ | grep -v "src/fleetent/tui/"` 应仅剩 `agent_app.py` 的 dispatch/protocol/transport 三行

## 2. 测试先行（红：先调整测试，暴露待删面）

- [ ] 2.1 删除纯客户端单测文件：`tests/unit/test_tui_app.py`、`test_tui_backend.py`、`test_tui_commands.py`、`test_tui_render.py`
- [ ] 2.2 编辑 `tests/unit/test_tui_logging.py`：移除 `tui.backend`、`tui.app` 两组用例，保留 `tui.transport`、`tui.dispatch` 用例；运行 `uv run pytest tests/unit/test_tui_logging.py -x -q` 见绿
- [ ] 2.3 运行保留的服务端测试确认当前全绿（删除前基线）：`uv run pytest tests/unit/test_tui_dispatch.py tests/unit/test_tui_dispatch_approve.py tests/unit/test_tui_dispatch_abort.py tests/unit/test_tui_protocol.py tests/unit/test_tui_transport.py tests/unit/test_agent_app_tui_auth.py -q` 与 `uv run pytest tests/integration/test_agent_runtime_ws.py tests/integration/test_tui_carries_principal.py -q`

## 3. 删除客户端模块（绿）

- [ ] 3.1 删除 `src/fleetent/tui/app.py`、`backend.py`、`commands.py`、`render.py`
- [ ] 3.2 更新 `src/fleetent/tui/__init__.py` docstring：由"Interactive terminal TUI client"改述为"`/ws` 网关服务端协议/调度/传输（dispatch/protocol/transport）"
- [ ] 3.3 运行 `uv run pytest tests/unit/test_tui_dispatch.py tests/unit/test_tui_protocol.py tests/unit/test_tui_transport.py tests/unit/test_tui_logging.py -q` + `uv run pytest tests/integration/test_tui_carries_principal.py tests/integration/test_agent_runtime_ws.py -q` 见绿（保留面不受影响）

## 4. 移除入口与安装脚本引用

- [ ] 4.1 `pyproject.toml`：删除 `fleetent-tui` console-script 入口
- [ ] 4.2 `scripts/install-platform.sh` / `scripts/install.sh`：去掉安装成功日志中的 `fleetent-tui`
- [ ] 4.3 `scripts/install-agent.sh`：去掉 "Connect TUI: fleetent-tui …" 提示与 `Installed: … fleetent-tui` 字样（保留 `FLEETENT_TUI_TOKEN` 写入 `.env` 的逻辑不动）
- [ ] 4.4 运行 `uv run pytest tests/integration/test_install_script.py -q`，确认无新增失败

## 5. 依赖收敛（条件执行，依据 task 1.1）

- [ ] 5.1 若 1.1 确认 `prompt_toolkit` / `rich` / `websockets` 仅客户端使用，从 `pyproject.toml` 依赖中移除；否则跳过并在 PR 描述注明保留原因
- [ ] 5.2 `uv sync` 后运行 `uv run pytest tests/unit -q`，确认无 import 断裂、无新增失败

## 6. 收尾验证

- [ ] 6.1 `make test-pr` 全绿（unit + 层边界 + changed-vs-main ruff）
- [ ] 6.2 `uv run pytest tests/integration -q`（不带 `-x`，对照 main 基线，无新增失败）
- [ ] 6.3 验证基线：`/ws` 服务端、`FLEETENT_TUI_TOKEN` 认证、`/chat` SSE、网页后台聊天均不受影响；`grep -rn "fleetent-tui\|tui/app\|tui/backend\|tui/commands\|tui/render" src tests scripts pyproject.toml` 仅剩文档/归档类历史引用
