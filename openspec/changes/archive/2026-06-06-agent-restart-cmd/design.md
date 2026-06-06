## Context

`fleetent agent run` 以前台阻塞进程运行，没有任何进程追踪机制。平台侧的 `AgentController` 维护内存级 PID 表，但仅供平台使用，且不持久化。agent 运行时 CLI 侧完全没有 restart 支持。

调用链：Slack 消息 → `normalizer._handle_message()` → `loop.run()` → agent 循环。
Drain 的目标是：停止接收新消息，等 `loop.run()` 的所有 in-flight 调用跑完，再退出。

## Goals / Non-Goals

**Goals:**
- 单命令重启 agent 进程，适用于脚本和运维场景
- Graceful drain：重启前等待 in-flight 请求跑完（默认超时 30s）
- 无额外运行时依赖（不引入 psutil 等新包）
- 静默处理进程已退出的情况（幂等性）

**Non-Goals:**
- 后台守护（restart 执行完后新进程仍为前台阻塞）
- 平台侧 API 触发 restart（本次只做 CLI）
- 健康检查或自动 restart watchdog

## Decisions

### D1：PID 文件写在 agent home 目录

**选择**：`<home_dir>/.fleetent.pid`（`.` 前缀隐藏，同 home 目录）

**理由**：无需数据库或进程注册中心，符合项目"self-contained home"原则；路径可由 `resolve_home()` 唯一确定，restart 命令不需要额外参数。

**替代方案**：`/tmp/fleetent-<agent-id>.pid`——路径固定但与 home 解耦，多实例同 id 会冲突。

---

### D2：`_stop_running` 在 `asyncio.run()` 之前同步调用

**选择**：在 `__main__.py` 中，先同步调用 `_stop_running(home_dir)`，再调用 `asyncio.run(serve(...))`。不设独立的 `restart()` async 函数。

**理由**：`_stop_running` 含同步轮询（`time.sleep`），放在 async 函数内会阻塞事件循环。CLI 入口不需要 async，分离更清晰。

**替代方案**：`restart()` async 函数内用 `asyncio.sleep` 轮询——复杂度高，收益为零，因为此时事件循环里没有其他并发任务。

---

### D3：SIGUSR1 触发 graceful drain，SIGTERM 保留为强制停止

**选择**：`_stop_running` 发送 SIGUSR1（drain 信号），等待 drain_timeout（默认 30s）；超时后降级 SIGTERM，再等 5s；最终 SIGKILL。

**理由**：SIGUSR1 是"请求优雅退出"的 Unix 惯例（Hermes、nginx 均如此）；SIGTERM 语义是"立即停止"，两者区分清晰。`serve()` 通过 `loop.add_signal_handler(SIGUSR1, ...)` 注册异步安全的 handler，在事件循环线程内处理。

**替代方案**：只用 SIGTERM——简单但无法区分"优雅重启"和"强制停止"，无法实现 drain。

---

### D4：active run 计数器放在 `runtime/loop.py`

**选择**：`loop.py` 模块级 `_active_runs: int`，在 `run()` 入口 +1、finally -1。`agent_app.py` import 这个计数器做 drain 等待。

```
loop.py:  _active_runs += 1 / -1   ← 计数紧贴实际运行点
agent_app.py:  while _loop._active_runs > 0: await asyncio.sleep(0.1)
```

**理由**：计数放在 `loop.run()` 里最准确；避免 normalizer ↔ agent_app 循环依赖（normalizer 不需要改动）。

**替代方案**：独立 `runtime/drain.py` 模块——多一个文件，当前规模不值得。

---

### D5：drain 期间停止接收新 IM 消息

**选择**：SIGUSR1 handler 触发后，调用 `rt.supervisor.stop_all()` 停止 Slack 连接，然后等 `_active_runs == 0`，再退出。

**理由**：已有的 `SlackSupervisor.stop_all()` 可直接复用；停止 IM 是 drain 的第一步，防止新消息进入。

## Risks / Trade-offs

- **PID 复用**：极少概率旧 PID 被 OS 分配给无关进程后被 SIGUSR1。缓解：`_stop_running` 只在 PID 文件存在时操作，且进程消失后立即返回，窗口极小。
- **PID 文件残留**：`serve()` 异常退出时 `finally` 块保证删除，不残留。
- **并发 restart**：两个 `restart` 同时执行会双写 PID 文件，产生竞态。缓解：CLI 工具由运维手动触发，并发概率极低，本次不加锁。
- **Drain 超时**：in-flight 请求超过 30s 未完成时，SIGTERM 强制中断。该对话对用户无响应。可通过配置 `FLEETENT_RESTART_DRAIN_TIMEOUT` 调整。
