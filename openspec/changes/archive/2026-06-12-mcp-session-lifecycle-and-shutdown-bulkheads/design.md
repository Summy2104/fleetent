## Context

崩溃因果链（2026-06-11，全程日志实证）：

```
14:51:31.411  agent_drain_started active_runs=3        ← SIGUSR1 优雅排水开始
              serve() finally → _drain_and_exit → rt.stop() → asyncio.run() 收尾
              事件循环 shutdown_asyncgens() 从主 task 强制 athrow 仍开着的
              streamablehttp_client 异步生成器（armada，启动时由别的 task enter）
14:51:31      RuntimeError: Attempted to exit cancel scope in a different task
              athrow(): asynchronous generator is already running
              BaseExceptionGroup → 反向 cancel 主 task scope（"Cancelled via cancel scope"
              贯穿 supervisor.stop_all 调用栈）→ Main process exited, status=1/FAILURE
```

anyio 硬约束：cancel scope / task group 的 enter 与 exit **必须同 task**。SDK 三种 transport
（`stdio_client` / `sse_client` / `streamablehttp_client`）内部均基于 anyio task group——
**约束对三种 transport 同等生效**。

现状违例点：
- `client.py:48` 模块级 `_exit_stack`；`:280-285` `get_exit_stack()` 懒初始化（首个使用者的
  task enter）；`:516-521` `_open_session_for` 把 transport CM + ClientSession enter 进共享栈
  ——boot task、Slack 消息 task（懒重连）混用；
- `client.py:289` `close()`：spec 要求的关停释放入口，**零调用方**（死代码）；
- `client.py:891` `_reopen_session`：只开新不关旧，泄漏；
- 排水链 `_drain_and_exit`：停 IM/调度 → 等排干 → 返回——**没有 MCP 释放步骤**，且各步无舱壁。

对照组（证明架构在、模式有先例）：`SlackSupervisor` 每连接一个 owner task，`stop()` 定向
cancel + gather——正是 owner-task 模式的 in-repo 正确实现。本 change 是把该模式推广到 MCP。

## Goals / Non-Goals

**Goals**
- MCP 会话生命周期纳编：每会话唯一 owner task，enter/exit 同 task，三 transport 统一。
- 关停链完整且有舱壁：停入口 → 排干 → 释放 MCP → exit 0；任一步失败不改变退出码。
- 懒重连不泄漏。
- 规则固化：AGENTS.md 契约 + guardrail 测试，违例死在 PR 门禁而非生产 teardown。

**Non-Goals**
- 不改 MCP 工具调用面（`_call_via_session`、降级/健康/超时语义、工具命名）。
- 不改 serve() 的 uvicorn/信号编排结构（只在 `_drain_and_exit` 内加步骤与舱壁）。
- 不引入 anyio TaskGroup 重写应用骨架（结构化并发全量化超出本步必要性）。
- SIGUSR1 发送者审计（当晚谁触发了 drain）为独立运维动作，不入本 change。

## Decisions

### D1. 会话宿主（per-session owner task）——三 transport 统一

```python
@dataclass
class _SessionHost:
    task: asyncio.Task[None]
    close_event: asyncio.Event
    session: Any  # ClientSession（ready 后可用）

async def _host_session(server, scope, headers, ready: asyncio.Future, close_event) -> None:
    try:
        async with _transport_cm(server, headers) as streams:          # enter ─┐
            read, write = streams[0], streams[1]                       #        │ 全程
            async with ClientSession(read, write, message_handler=...) as session:  # 同一 task
                init = await session.initialize()                      #        │
                if not ready.done():
                    ready.set_result((session, init))
                await close_event.wait()                               # 驻留   │
    except Exception as exc:                                           # exit ──┘
        if not ready.done():
            ready.set_exception(exc)          # 打开失败 → 调用方按既有注册失败路径处理
        else:
            logger.warning("mcp_session_teardown_failed server_id=%s error=%s", server.id, exc)
```

`_open_session_for`：spawn 宿主 → `await ready`（沿用 `connect_timeout`）→ 存
`_active_sessions[(scope, id)] = host` → 返回 `host.session`。调用方（注册、`_call_via_session`、
懒重连）只消费 session 句柄，接口不变。

边界语义：`close_event` 先于 ready 被 set（极端竞态）→ 宿主正常退出、ready 以取消语义收尾；
重复 close 幂等（event 可重复 set，task await 幂等）。

### D2. `aclose_all()` 与关停接线

```python
_HOST_CLOSE_TIMEOUT = 5.0  # 可注入常量（测试 monkeypatch）

async def aclose_all() -> None:
    hosts = list(_active_sessions.values()); _active_sessions.clear()
    async def _close(h):
        h.close_event.set()
        try:
            await asyncio.wait_for(asyncio.shield(h.task), _HOST_CLOSE_TIMEOUT)
        except TimeoutError:
            h.task.cancel()
            await asyncio.gather(h.task, return_exceptions=True)
        except Exception as exc:  # 宿主已自吞 teardown 异常，这里只兜元层错误
            logger.warning("mcp_host_close_failed error=%s", exc)
    await asyncio.gather(*(_close(h) for h in hosts), return_exceptions=True)
```

接线（顺序即契约）：
- agent 侧 `_drain_and_exit`：`rt.stop()`（停 IM+调度，已有）→ 排干等待循环（已有）→
  **`aclose_all()`（新增）** → 返回。MCP 必须在排干**之后**关——在飞 run 还在用工具。
- platform 侧 `server.py` lifespan shutdown：`aclose_all()`（platform 经 admin `register_all`/
  probe 也持有会话）。

### D3. 舱壁（containment law）

`_drain_and_exit` 与 `AgentRuntime.stop()` 内每个组件的停止包裹为：

```python
async def _stop_step(name: str, coro: Awaitable[None], timeout: float = 10.0) -> None:
    try:
        await asyncio.wait_for(coro, timeout)
    except Exception as exc:  # noqa: BLE001 — 收尾错误只记录，绝不外泄
        _logger.warn("shutdown_step_failed", step=name, error=str(exc))
```

不变式：**优雅路径退出码恒为 0；任何组件收尾错误不得跨组件传播**。该不变式由注错测试钉住。

### D4. 懒重连关旧

`_reopen_session`：取出旧 host（若有）→ `close_event.set()` + 限时等待（失败仅记日志）→
按 D1 开新。修正"重连即泄漏"。

### D5. 契约固化与护栏

- AGENTS.md 架构契约区追加：「**长生命周期异步资源（连接、会话、子进程流）必须有唯一 owner
  task：谁打开谁关闭；跨 task 只传句柄、不传生命周期操作；禁止模块级持有活资源的全局单例**」
  ——既有第 154 行风格铁律的异步资源细化，IM supervisor 与 MCP 宿主为两个范式实现。
- guardrail（`test_module_dependency_guardrails.py` 新增）：扫描 src 模块作用域的
  `AsyncExitStack` 实例化/持有（AST 或正则级，与现有护栏同风格）。现存唯一违例 = 本 change
  删除的 `_exit_stack` → 护栏先红、重构后绿，并阻止回潮。

## Alternatives considered

- **保留全局栈，由"打开者 task"负责关闭**：打开者是短命的消息处理 task，无法承担进程级关停责任。否决。
- **每次工具调用临时开关会话**：时序正确性最简单，但 stdio 每次调用要拉子进程、http 每次
  握手+initialize，延迟与成本不可接受；且违背 spec 既有「会话复用」要求。否决。
- **anyio TaskGroup 结构化重写 serve()**：根治性更强但触面（uvicorn/slack-bolt/APScheduler
  混生态）与回归风险远超必要；宿主模式以 ~200 行达成同等不变式。否决（可作长期方向另议）。
- **只修 streamable-http**：三 transport 同为 anyio 实现，同病；只修一处留两处地雷且模式分裂。否决。

## Risks / Trade-offs

- **每服务常驻一个宿主 task**：本地 7 个 MCP server ≈ 7 个驻留 task，开销可忽略；换来生命周期
  确定性。
- **ready/close 竞态**：以单测显式覆盖（close-before-ready、double-close、open 失败传播）。
- **关闭超时取舍**：5s/宿主 + 并发关闭，最坏新增 ~5s 关停时长；超时 cancel 兜底保证有界。
- **行为收紧面**：优雅重启从"必崩（exit 1）"变为"必须 exit 0"——验收口径反转，部署脚本无需改
  （systemd `Restart=on-failure` 对 exit 0 不再误触发重启竞态）。

## Test strategy（TDD，红→绿）

- **同 task 断言（unit，核心红绿）**：stub transport CM 记录 `asyncio.current_task()` 于
  `__aenter__`/`__aexit__`；task A 打开、task B 触发关闭 → enter/exit 同（宿主）task、无异常。
  现行全局栈实现必跨 task → 红。
- **舱壁注错（unit）**：stub CM `__aexit__` 抛 RuntimeError → `aclose_all()` 不外泄、记 warning；
  `_stop_step` 注入抛错组件 → 后续步骤照常执行。
- **重连关旧（unit）**：`_reopen_session` 后旧宿主 task `done()`、registry 无孤儿。
- **排水顺序（integration）**：以 stub 组件跑 `_drain_and_exit` → 调用序为 stop → drain →
  aclose_all；全程模拟收尾错误，退出路径正常返回。
- **护栏（unit）**：guardrail 测试先红（现存 `_exit_stack`）→ 重构后绿。
- **实机验收（部署后）**：dev-intern 连续 20 次 SIGUSR1 优雅重启 → 每次 exit 0、零 traceback、
  Slack 连接恢复；运行中掐断 armada 网络 → 进程存活、工具按既有 degrade 降级。
- 收尾：`make test-pr` + `uv run pytest tests/integration -q` 对照 main 基线无新增失败。
