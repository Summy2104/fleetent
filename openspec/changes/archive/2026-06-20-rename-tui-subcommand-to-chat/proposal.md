## Why

`fleetent tui` 子命令名是实现术语(terminal UI),对用户不直观——敲 `fleetent tui` 看不出是干嘛。`chat` 是交互语义、一眼即懂,且是未来"终端渠道双形态(本地进程内 + 远程)"统一入口的注定命名。趁 `fleetent tui` 刚落地、尚无外部依赖,直接改名 `chat`,避免将来 tui→chat 的改名 churn,也不用背 jargon。**纯改名,行为不变**(仍是连远程 `/ws` 的客户端);将来本地形态在同名 `chat` 下长出来。

## What Changes

- **`fleetent tui` → `fleetent chat`**:`__main__.py` 分支判定 `tui`→`chat`;`tui/app.py` 的 `prog="fleetent tui"`→`"fleetent chat"`。客户端逻辑、`/ws` 服务端、斜杠命令全不变。
- **下游同步**:install 脚本(install.sh / install-agent.sh)、README/AGENTS.md/.env.example、安装测试断言、4 个 spec(agent-runtime-cli / tui-gateway / install-bootstrap / install-agent-script)中的 `fleetent tui` → `fleetent chat`。

**不动(实现层,刻意保留)**:内部 `tui/` 包名、`tui-gateway` capability 名、`/ws` 端点、`FLEETENT_TUI_URL`/`FLEETENT_TUI_TOKEN`/`FLEETENT_TOKEN` 环境变量——改它们是无谓 churn(尤其 env 变量改名是另一层 breaking)。本 change 只动用户可见的子命令名。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities

- `agent-runtime-cli`:REMOVE「`fleetent tui` 子命令」+ ADD「`fleetent chat` 子命令」(命令改名)。
- `tui-gateway`:MODIFY「终端 TUI 客户端」——入口 `fleetent tui` → `fleetent chat`(客户端能力不变)。
- `install-bootstrap`:MODIFY「Global command installation」——终端客户端经 `fleetent chat`。
- `install-agent-script`:MODIFY 教程——连接改用 `fleetent chat`。

## Impact

**owning package**:`src/fleetent/__main__.py`、`src/fleetent/tui/app.py`(仅命令名/prog)

**public API surface**:`fleetent tui` → `fleetent chat`(子命令改名)。**BREAKING**(轻):`fleetent tui` 刚落地、无外部依赖,直接改不留别名。

**owned tables**:无　**config namespace**:无(env 变量不改)　**migration**:无

**cross-module dependencies**:无变化(仍懒加载 `tui.app`)

**下游引用**:install.sh / install-agent.sh、test_install_script.py / test_install_agent_script.py、test_main_subcommands.py、README.md、AGENTS.md、.env.example
