## Why

node 的 `LocalProcessBackend.spawn` 用 `subprocess.Popen(...)` 启动 agent 但**丢弃句柄、父进程从不 `waitpid` 回收**;`is_alive` 用 `os.kill(pid, 0)` 探活,而该调用对**僵尸(defunct)进程返回成功**——被 kill 或自行崩溃的 agent 子进程变僵尸后被永久判为"存活",node reconcile 因此**永不重新拉起它**。现有 spec 已规定"stale PID(进程已死)SHALL 判为不存活",僵尸正是这条规则未覆盖的失真变体。生产后果:agent 崩溃后不自愈,需重启整个 node 才能恢复(2026-06-25 live e2e 实测)。

## What Changes

- **修复** `LocalProcessBackend.spawn`:保留 `Popen` 句柄(`self._procs[agent_name]`),使 node 成为可回收其子进程的父进程
- **修复** `LocalProcessBackend.is_alive`:在 `os.kill(pid, 0)` 之外,对本 node 启动的 agent 先做非阻塞回收(`proc.poll()`)并以 `returncode` 判定——已退出(含僵尸)的子进程 SHALL 判为不存活;`returncode` 守护同时消除 PID 复用导致的误判
- **修复** `LocalProcessBackend.stop`:CLI 优雅停后回收并清理本地句柄,避免僵尸残留
- **保持** PID 文件作为真相源的 re-adopt 语义不变(node 重启后无句柄,旧子进程已被 init 回收,`os.kill` 判活恢复准确)
- 纯 stdlib 实现,不引入 `psutil` 等新依赖

## Capabilities

### New Capabilities

(无新增 capability)

### Modified Capabilities

- `node-process-backend`:`local 进程后端`的 `is_alive` 行为补充——已退出/僵尸子进程判不存活;新增 spawn 句柄保留与子进程回收要求

## Impact

- `src/fleetent/node/backend.py`:`LocalProcessBackend` 增加 `_procs` 句柄表;`spawn`/`is_alive`/`stop` 三方法调整(public 方法签名不变)
- `tests/unit/node/test_backend.py`:新增僵尸/已退出子进程判不存活的红/绿测试
- owning package:`node`(单包改动,不碰其他模块)
- owned tables / config namespace:无
- cross-module dependencies:无新增;不依赖任何其他模块 public API
- migration / shim:无(行为修复,接口不变)
