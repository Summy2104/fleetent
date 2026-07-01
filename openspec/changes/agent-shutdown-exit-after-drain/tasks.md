# Tasks:agent-shutdown-exit-after-drain(问题 ④)

标记:`[服务器]` 需真实数据/活体进程;`[本地]` 纯代码+mock/tmp_path 单测。

## 诊断(先行)—— 已完成(2026-06-30,部署机,只读 /proc)
- [x] [服务器] 只读检查运行中 alpha agent:8 个 stdio MCP 子进程 + 线程 wchan = `8×do_wait`(waitpid on 子进程)/`1×ep_poll`/`4×futex`。
- [x] [服务器] 产出"卡住资源清单 + 修复方向" → 见 proposal.md「活体诊断结果」。结论:MCP stdio 子进程(及孙子进程)teardown 未强制终止 → waitpid 线程不返回 → 进程不 exit → SIGKILL。
- [ ] [服务器,可选] 待本地写出修复后,catch 一次真实重启的 drain 窗口(py-spy)做最终确认。

## 实现(TDD,test 先于 impl)
- [ ] [本地] 写测试:模拟 `_drain_and_close` 在 `active_runs=0` 完成后,关停编排会**驱动 event loop 停止 / 进程退出路径**被调用(见红)。
- [ ] [本地] 实现:`agent_drain_completed` 之后确定性触发退出(停 loop / server.shutdown / `sys.exit(0)`),关停链每步舱壁化(独立 try/except+超时)(见绿)。
- [ ] [本地] 写测试:某个收尾子步骤抛异常时,其它组件仍被收尾、退出码仍为 0(舱壁化)(见红→绿)。
- [ ] [本地] 按诊断清单,确保存活资源在 drain 内被各自 owner task 关闭(不新增模块级 `AsyncExitStack` 单例;护栏须绿)。
- [ ] [本地] (可选)`_stop_running`:确认 drain 完成后不空等满 30s。

## 收尾
- [ ] [本地] `make test-pr` + `make test-integration-ci` 全绿(无新增失败)。
- [ ] [服务器] 部署(reinstall --no-cache + restart platform/node)。
- [ ] [服务器] 验收:触发重启 → journal `agent_process_exited_gracefully`,无 `agent_force_kill`,无 `RemoteProtocolError` 丢消息窗口。
