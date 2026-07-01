# 变更:agent 排空后必须真正退出(消除 force-kill churn)

母文档:`docs/records/aaa-8204-recovery.md`(问题 ④)

## 为什么

托管部署里 agent 进程被 node 反复重启(配置变更触发 reconcile 是**正常触发**),但**关停执行是 bug**:

- `_stop_running`(`src/fleetent/runtime/agent_app.py:627`)Phase1 发 `SIGUSR1`→打 `agent_drain_requested`,随后轮询 `os.kill(pid,0)` 最多 `drain_timeout`(30s)等**进程退出**;Phase2 SIGTERM 等 5s;Phase3 `SIGKILL`。
- SIGUSR1 handler 触发 `_drain_and_close`(`:133`),排空在飞 run 后打 `agent_drain_completed`(`:150`)。
- 实测:全天 17 次重启,15 次 `agent_drain_completed` 且 `active_runs=0`,在 **~200ms 内**完成排空——**但进程没有退出**,还扛过了 5s SIGTERM,17 次全部走到 `agent_force_kill`。

后果:每次重启留出 ~30–35s 的下线窗口,期间 node→agent 的 `_forward_inbound` 报 `httpx.RemoteProtocolError: Server disconnected` / `All connection attempts failed`,**落窗口的入站消息(含 `approve <id>`)被静默丢弃**,放大了 ①②③ 的所有现象。

根因:**排空完成后进程没有走到真正的 `exit(0)`**——疑似有长生命周期异步资源/非 daemon task(MCP session host、IM 连接、uvicorn server 等)在 drain 后仍存活,使 loop 不停、进程不退,且 SIGTERM 也被拦/无效。对应 `AGENTS.md` 的「owner-task 契约」与「优雅排水路径必须 exit 0」。

## 改动

1. `_drain_and_close` 收尾(`agent_drain_completed` 之后)必须**确定性地驱动进程退出**:停 event loop / 关 server / `sys.exit(0)`,且关停链每一步**舱壁化**(独立 try/except + 超时),单组件收尾失败只记日志、不阻塞退出。
2. 找到并关闭 drain 后仍存活的资源/task(服务器侧活体诊断给出具体清单后,本地按清单收口)。
3. (可选)`_stop_running` 在确认 `agent_drain_completed` 后无需空等满 30s——但**首要是让进程真退出**,缩短超时是次要优化。

## 模块边界影响

- **owning package**:`runtime/`(`agent_app.py`)。
- **public API surface**:`serve()` / `_stop_running()` 行为不变(签名不变),仅修关停语义。
- **owned tables**:无。
- **config namespace**:无(沿用 `drain_timeout`)。
- **cross-module dependencies**:遵守「谁打开谁关闭」owner-task 契约;不得新增模块级全局 `AsyncExitStack` 单例(护栏 `test_no_module_level_asyncexitstack_singleton`)。
- **migration / shim**:无。

## 分工

- **服务器(我)**:对一个真 agent 发 SIGUSR1,用 faulthandler / py-spy dump `agent_drain_completed` 之后仍存活的 task/线程/fd,给出"是谁不让它退"的具体清单;部署后验收。
- **本地(你)**:按清单收口关停链 + 写单测(见 tasks.md),保证 drain 完成后进程 exit(0)。

## 活体诊断结果(2026-06-30,部署机侧,纯只读 /proc,未发信号/未重启)

对运行中 alpha agent(pid 1511923)做只读检查:

- 它**直接拉起 8 个 stdio MCP 子进程**:`@aashari/...-bitbucket`、`...-confluence`、`...-jira`(均 `npm exec`)、`@piotr-agier/google-drive-mcp`(npm)、`slack-mcp-server`(node)、`mcp-image-recognition`(node)、`mcp-email-server`(uvx)、`@playwright/mcp --browser chromium --headless`。多数是 npm/node 包装,**还带孙子进程**(如 slack-mcp-server → `...-linux-amd64`,bitbucket → `mcp-atlassian-bitbucket`)。
- 线程 `wchan` 分布:`1×ep_poll`(asyncio 事件循环)、**`8×do_wait`(= `waitpid` 阻塞在 8 个 MCP 子进程上)**、`4×futex`(锁/线程池)。
- **8 个 `do_wait` 线程一一对应 8 个 MCP 子进程**。

根因链:drain 后 `mcp.aclose_all()` 关 stdio 会话仅"关 stdin + 等子进程退";npm/node/chromium 系子进程收到 stdin 关闭/SIGTERM **不一定退**(尤其杀父不杀孙),`waitpid` 永久阻塞;且该阻塞**不响应 `asyncio.wait_for` 的取消**,使 `_stop_step` 的 10s 超时形同虚设 → `_drain_and_close` 卡住 → `serve()` 不返回 → 进程不 exit、扛过 SIGTERM、只能被 SIGKILL。

### 卡住资源清单(本地按此收口)
- 8 个 stdio MCP 子进程(及其孙子进程),teardown 时未被强制终止 → 8 个 `waitpid` 线程不返回。
- 重点嫌疑:有孙子进程的 npm 包装类(bitbucket/confluence/jira/google-drive/slack)与 chromium(playwright)。

### 修复方向(本地)
1. MCP stdio 会话 teardown **有界 + 强制**:关 stdin 后限时等,超时则对子进程**进程组** SIGTERM→SIGKILL(杀整棵树含孙子进程),保证 `waitpid` 线程返回。
2. 让 `_stop_step` 的取消能真正中断"等子进程退出"(把等待做成可取消/到点就杀)。
3. 兜底:drain 后限定时间内仍未干净退出,`os._exit(0)`(优雅排水路径必须 exit 0)。
4. 遵守 owner-task 契约:每个 session 的 transport/子进程由其 owner task enter/exit。

## 验收

改一次配置触发重启,journal 出现 `agent_process_exited_gracefully`(而非 `agent_force_kill`);重启期间 `_forward_inbound` 不再 `RemoteProtocolError`;连续改配置不再制造 ~35s 下线窗口。
