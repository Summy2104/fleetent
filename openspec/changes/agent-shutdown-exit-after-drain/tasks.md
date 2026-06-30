# Tasks:agent-shutdown-exit-after-drain(问题 ④)

标记:`[服务器]` 需真实数据/活体进程;`[本地]` 纯代码+mock/tmp_path 单测。

## 诊断(先行)
- [ ] [服务器] 对一个真 agent 进程发 `SIGUSR1`,观察 journal 确认 `agent_drain_completed` 后进程是否退出;用 faulthandler/py-spy dump 存活的 task/线程/打开的连接(MCP session host、IM 连接、uvicorn server、其它非 daemon task)。
- [ ] [服务器] 产出"drain 后阻止退出的资源清单",回填本文与 proposal。

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
