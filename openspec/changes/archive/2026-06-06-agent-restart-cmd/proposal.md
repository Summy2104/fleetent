## Why

`fleetent agent run` 启动的进程没有重启机制；运维需要手动 kill 再 re-run，步骤易出错且无法脚本化。增加 `fleetent agent restart` 命令，让单条命令完成「停旧 → 启新」。

## What Changes

- `fleetent agent run` 启动时写 PID 文件（`<home>/.fleetent.pid`），退出时删除
- 新增 `fleetent agent restart <agent-id> [--port N] [--home PATH]` 命令
  - 读取 PID 文件 → SIGTERM 旧进程 → 等待退出（最多 5 秒，超时后 SIGKILL）→ 以相同参数启动新进程（前台阻塞）
  - PID 文件不存在或进程已退出时，静默跳过 kill，直接启动

## Capabilities

### New Capabilities

无

### Modified Capabilities

- `agent-runtime-cli`：新增 `restart` 子命令要求；`serve()` 需维护 PID 文件生命周期

## Impact

- `src/fleetent/runtime/agent_app.py`：新增 `_stop_running()`、`restart()`，`serve()` 写/删 PID 文件
- `src/fleetent/__main__.py`：新增 `_parse_agent_restart()` 和 `agent restart` 分发分支
- `tests/unit/test_agent_run_cli.py`：新增 restart 相关测试用例
