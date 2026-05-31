## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 AR5 `error_classifier`：`CLASSIFICATION_TABLE[ErrorCategory.mcp_disconnect]`（error_classifier.py 行 91）为 `should_retry=True`；确认 `classify()`/`_categorize()`（行 97-119）仅识别 `APIStatusError`、对断连异常（httpx ConnectError / stdio EOF）返回 `unknown` 而**非** `mcp_disconnect`——据此定 D1：mcp_client 侧把断连异常判定为 `ErrorCategory.mcp_disconnect`、直接读 `CLASSIFICATION_TABLE[mcp_disconnect]` 取标志位，**不经 `classify()`**，不改 AR5 表
- [x] 1.2 核实断连异常形态：HTTP 走 httpx（`ConnectError`/`ConnectTimeout`/`ReadError` 等，`_call_http_tool` 行 312）、stdio 子进程死亡/会话失活（`_call_stdio_tool` 行 302，`_active_sessions`）的异常表现
- [x] 1.3 核实 `register_all`（行 117）/ `close()`（行 108）/ server.py lifespan（行 82-87、110）的启停接入点；确认探活后台任务的启动/取消位置
- [x] 1.4 核实 server.py lifespan 的后台 task 启停钩子（`mcp_client.register_all` / `close` 同处），确认探活用裸 `asyncio.create_task` 即可、无需新增调度依赖、且不挂 `cron_scheduler`（与暂缓的定时任务功能解耦）
- [x] 1.5 核实与 MCP2 的边界：404（会话过期，MCP2 重建）与连接级断连（本 change）如何区分（D7），确认 404 不进本 change 降级路径

## 2. 连接健康状态（mcp_client.py）

- [x] 2.1 Write failing tests：服务健康状态三态（`healthy` / `degraded` / `unavailable`）按 server 隔离持有；默认 `healthy`；可注入/重置；不同 server 状态互不影响。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement 连接健康状态（按 server 实例持有，不进模块级可变全局），看到绿

## 3. 接通 AR5 mcp_disconnect 路径（断连分类与降级）

- [x] 3.1 Write failing tests：断连异常（httpx 连接错误 / stdio 会话失活）由 mcp_client 侧判定为 `ErrorCategory.mcp_disconnect`、直接读 `CLASSIFICATION_TABLE[mcp_disconnect]` 得 `should_retry` 为真；据此把服务转 `degraded`。守卫用例：断言 `classify(断连异常)` 仍为 `unknown`（证实不经 `classify()`、不依赖其识别断连）。mock 断连异常。看到红
- [x] 3.2 Implement：工具调用捕获断连异常 → mcp_client 侧判定为 `ErrorCategory.mcp_disconnect`、直接读 `error_classifier.CLASSIFICATION_TABLE[mcp_disconnect]`（不经 `classify()`、不改 AR5 表）→ 依 `should_retry` 转降级/重连，看到绿
- [x] 3.3 Write failing tests 降级反馈：服务处于 `degraded` / `unavailable` 时，对其工具的调用返回「服务暂时不可用」文本，不抛异常、不进真实网络/子进程调用；其他健康服务工具不受影响。看到红
- [x] 3.4 Implement 降级期工具返回「服务暂时不可用」，看到绿
- [x] 3.5 Write failing test 区分会话过期与连接断连：HTTP 404（会话过期）不进本 change 的连接降级路径、不归 `mcp_disconnect`（与 MCP2 分层）。看到红
- [x] 3.6 Implement 使 404 与连接断连区分通过（D7），看到绿

## 4. 周期探活

- [x] 4.1 Write failing tests：探活检测到 HTTP 服务不可达 / stdio 子进程不存活时，把服务转 `degraded` 并触发重连入口。respx mock HTTP 探活、unittest.mock mock stdio 会话；探活间隔用可注入短值。看到红
- [x] 4.2 Implement 周期探活（HTTP 轻量请求 / stdio 子进程存活检查；间隔可注入），看到绿

## 5. 指数退避重连与永久不可用

- [x] 5.1 Write failing tests 退避序列：重连退避按 1→2→4→…→上限 60s（用可注入基数/上限的短值断言序列封顶），不真实长 sleep。看到红
- [x] 5.2 Implement 指数退避计算（基数/上限可注入），看到绿
- [x] 5.3 Write failing tests 恢复：重连成功 → 状态回 `healthy`、退避计数清零、工具自动重新可用。respx mock 重连成功响应。看到红
- [x] 5.4 Implement 重连成功后自动恢复，看到绿
- [x] 5.5 Write failing tests 永久不可用：连续失败达可注入阈值 → 转 `unavailable`、停止自动重连；手动触发重连入口可使其重新尝试并恢复。看到红
- [x] 5.6 Implement 达阈值标记 `unavailable` 与手动重连入口，看到绿

## 6. 后台任务接入 lifespan

- [x] 6.1 Write failing tests：探活/重连后台任务在服务启动时启动、关停（`close()`）时取消，不残留任务；CLI 一次性 `run()` 不常驻探活。看到红
- [x] 6.2 Implement 探活后台任务接入 server.py lifespan（MCP 域内 `asyncio.create_task` 常驻循环，关停随 `mcp_client.close()` 取消；不挂 cron_scheduler/APScheduler，不新增依赖），看到绿

## 7. 收尾

- [x] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 7.3 `uv run mypy src` 无新增错误
