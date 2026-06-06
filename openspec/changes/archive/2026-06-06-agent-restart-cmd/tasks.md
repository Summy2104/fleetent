## 1. Active run 计数器（`runtime/loop.py`）

- [x] 1.1 Write failing tests: `loop.run()` 执行期间 `_active_runs` +1，结束后 -1，异常时也 -1
- [x] 1.2 Implement: `loop.py` 加模块级 `_active_runs: int = 0`，在 `run()` 入口 +1 / finally -1

## 2. PID 文件：`serve()` 生命周期管理

- [x] 2.1 Write failing tests: `serve()` 写 PID 文件（运行期间文件存在且为当前 PID）、退出后删除
- [x] 2.2 Implement: `serve()` 加 `home_dir.mkdir(parents=True, exist_ok=True)` + `pid_file.write_text(str(os.getpid()))` + `finally: pid_file.unlink(missing_ok=True)`

## 3. Graceful drain：SIGUSR1 handler

- [x] 3.1 Write failing tests: `serve()` 收到 SIGUSR1 后停止 IM supervisor、等待 `_active_runs == 0`、然后退出
- [x] 3.2 Implement: `serve()` 用 `loop.add_signal_handler(SIGUSR1, ...)` 注册 handler；handler 触发 asyncio.Event；drain 协程 stop_all() + 轮询计数器 + 超时退出

## 4. `_stop_running()`：SIGUSR1 → SIGTERM → SIGKILL

- [x] 4.1 Write failing tests: 发送 SIGUSR1（而非 SIGTERM）、drain_timeout 内进程退出时成功、超时后降级 SIGTERM、stale PID 静默处理、无 PID 文件时无操作
- [x] 4.2 Implement: `_stop_running(home_dir, *, drain_timeout=30.0)` — 读 PID 文件 → SIGUSR1 → 轮询 drain_timeout → SIGTERM → 轮询 5s → SIGKILL → 删文件

## 5. CLI 分发

- [x] 5.1 Write failing tests: `_parse_agent_restart` 参数解析、`fleetent agent restart` 先调 `_stop_running` 再调 `asyncio.run(serve(...))`
- [x] 5.2 Implement: `__main__.py` 加 `_parse_agent_restart()` 和 `argv[:2] == ["agent", "restart"]` 分支（同步调 `_stop_running`，再 `asyncio.run(serve(...))`，不设独立 `restart()` 函数）

## 6. 收尾

- [x] 6.1 运行全量测试 `uv run pytest -x -q` 确认全绿
- [x] 6.2 运行 `uv run python scripts/check_test_layers.py` 确认测试层边界
