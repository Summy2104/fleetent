## Why

`fleetent-tui` 是独立 console-script,但它本质是 `fleetent` 工具族的一个交互入口。这条 CLI 合并线已把 admin/node 收进 `fleetent` 子命令、删了独立 binary;TUI 是最后一个游离入口。本 change 把它收成 `fleetent tui` 子命令(**纯打包合并,客户端行为不变**),安装入口从 4 路收敛到 1 路。顺带删掉 admin_cli 的孤儿文件 `observability.py`(slim 时移出 `_COMMAND_MODULES` 但未删文件)。

终端渠道的"远程 WS vs 本地进程内"形态决策**本 change 不做**(deferred);只挪入口、不改语义。

## What Changes

- **`fleetent-tui` → `fleetent tui` 子命令**:`tui/app.py` 的 `main()` 参数化(`argv` + `prog="fleetent tui"`);`__main__.py` 新增 `tui` 分支懒加载转发。客户端(`app.py`/`backend.py`/`commands.py`/`render.py`)与 `/ws` 服务端**全部保留不变**。
- **移除 `fleetent-tui` console-script**(`pyproject.toml`)。**BREAKING**:`fleetent-tui` 命令不再存在,改用 `fleetent tui --url <ws> --token <key>`。
- **删孤儿文件**:`admin_cli/observability.py`(无人 import、不在 `_COMMAND_MODULES`)。
- **作废 remove-tui-client**:那个 PARKED 的 change 前提是"删 TUI 客户端",与本决策(保留客户端、挪入口)相反,删除其 change 目录。
- **下游同步**:install 脚本(3)、install-bootstrap / install-agent-script / tui-gateway specs、README/AGENTS.md、安装测试,把 `fleetent-tui` 改为 `fleetent tui`。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities

- `agent-runtime-cli`:ADD `fleetent tui` 子命令 requirement。
- `tui-gateway`:MODIFY「终端 TUI 客户端」——入口由 `fleetent-tui` 改为 `fleetent tui` 子命令(客户端能力不变)。
- `install-bootstrap`:MODIFY「Global command installation」——只安装 `fleetent`(tui 经子命令)。
- `install-agent-script`:MODIFY 教程——连接改用 `fleetent tui`。

## Impact

**owning package**:`src/fleetent/__main__.py`(加 tui 分支)、`src/fleetent/tui/app.py`(main 参数化)、`pyproject.toml`(删入口);删 `admin_cli/observability.py`

**public API surface(移除)**:`fleetent-tui` console-script(等价能力经 `fleetent tui`)

**owned tables**:无　**config namespace**:无(`FLEETENT_TUI_URL`/`FLEETENT_TOKEN` 环境变量不变)　**migration**:无

**cross-module dependencies**:`__main__.py` 懒加载 `tui.app`(仅进 tui 分支触发,不影响 agent run 路径);`/ws` 服务端(`tui.dispatch/protocol/transport`)不变

**下游引用**:install.sh / install-platform.sh / install-agent.sh、test_install_script.py / test_install_agent_script.py、README.md、AGENTS.md、.env.example(env 变量保留,注释提示改 `fleetent tui`)

**与 remove-tui-client 的关系**:本 change 取相反方向(保留客户端),作废并删除该 PARKED change。
