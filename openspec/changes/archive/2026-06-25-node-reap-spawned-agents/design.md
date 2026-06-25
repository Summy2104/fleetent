## Context

`LocalProcessBackend`(`node/backend.py`)管理本地 agent 进程,设计上以 `<home>/.fleetent.pid` 为真相源(支撑 node 重启后 re-adopt 既有进程,不依赖守护内存)。

当前实现的缺陷:
- `spawn` 调 `subprocess.Popen(...)` 后**不保留返回的 Popen 对象**,node 进程作为父进程从不对子进程 `waitpid`。
- 当 agent 子进程退出(崩溃、被 kill、或 `agent stop` 后),在父进程回收前它处于 **zombie/defunct** 状态——进程表项仍在。
- `is_alive` 的 `os.kill(pid, 0)` 对僵尸进程**不抛 `ProcessLookupError`**(返回成功),于是判活为真。reconcile 的重拉分支(`if pid is None`)永不触发。

2026-06-25 live e2e 实测:外部 kill agent 子进程 → 它挂在 node 名下成 `<defunct>` → node 持续判活、不 respawn;只有杀掉 node(子进程 reparent 到 init 被回收)才恢复。

## Goals / Non-Goals

**Goals:**
- 被 kill/崩溃的 agent 子进程能被 node 正确判为不存活,触发 reconcile 自动重拉
- 不累积僵尸进程(node 回收自己 spawn 的子进程)
- 消除 PID 复用导致的误判
- 保持 PID 文件真相源 + re-adopt 语义不变
- 纯 stdlib,无新依赖

**Non-Goals:**
- 不改 reconcile 的重拉逻辑(`is_alive → None` 即重拉的现有行为已正确,本 change 只让 `is_alive` 说真话)
- 不改 `stop` 的优雅 drain 语义(仍走 `fleetent agent stop` CLI)
- 不实现 systemd 等其他后端
- 不修"只注入 secret 不触发重物化"那个独立 bug(`_config_hash` 不含 secrets,另案)

## Decisions

### D1:spawn 保留 Popen 句柄,is_alive 先回收再判

**决定**:
- `spawn`:`self._procs[agent_name] = subprocess.Popen(...)`,保留句柄。
- `is_alive`:若本 node 有该 agent 的句柄,先 `proc.poll()`(非阻塞,退出则回收、清除僵尸并置 `returncode`);随后:
  - 若 `proc.returncode is not None` → 子进程已退出 → 返回 `None`(权威,优先于 PID 文件)。
  - 否则走既有 PID 文件 + `os.kill(pid, 0)` 路径。
- `stop`:CLI 停止后 `proc.poll()` / 清理 `self._procs[agent_name]`,避免句柄泄漏与僵尸。

`returncode` 守护的额外收益:即便 PID 被系统复用、`os.kill(pid,0)` 对新进程返回成功,本 node 已退出的句柄仍判 `None`,不误判。

**备选**:
- 用 `psutil` 查进程状态过滤 `STATUS_ZOMBIE`。弃用:引入新依赖,违反项目"能自托管/最小依赖"取向,且 stdlib 已足够。
- 在 `is_alive` 里对所有 pid 无差别 `os.waitpid(pid, WNOHANG)`。弃用:`waitpid` 只能回收**本进程的子进程**,re-adopt 的非子进程会抛 `ECHILD`;且无句柄时拿不到 `returncode`。保留句柄 + `poll()` 更精确。

### D2:re-adopt(无句柄)路径保持 os.kill 探活

node 重启后 `self._procs` 为空,此时依赖 PID 文件 + `os.kill`。这条路径**仍然正确**:node 一旦退出,它 spawn 的子进程被 reparent 到 init(pid 1)并被回收,不再是僵尸;`os.kill(旧pid, 0)` 对真正消失的 pid 抛 `ProcessLookupError` → 判不存活。僵尸只会出现在"父进程(本 node)还活着但没回收"的窗口,而那个窗口里本 node 一定持有句柄,走 D1 的回收路径。

## Risks / Trade-offs

- **句柄表与 PID 文件可能短暂不一致** → D1 让 `returncode` 优先,且 `poll()` 每次 `is_alive` 调用都跑,窗口极小;reconcile 每轮(10s)收敛。

- **stop 之后句柄清理时机** → 在 `stop` 末尾 `poll()` 回收;若 CLI stop 抛错(`check=True`),回收应放在 try/finally 或 stop 失败后下一轮 is_alive 的 poll 兜底,避免句柄泄漏。实现时注意不吞 stop 的异常(项目铁律),回收用独立 finally。

- **测试需覆盖真实僵尸语义但单测用 mock** → 现有 `test_backend.py` 以 mock `Popen`/`os.kill` 为模式;新测试构造一个 `poll()` 后 `returncode` 非 None 的 fake proc + `os.kill` 仍成功,断言 `is_alive` 返回 `None`(精确复现僵尸:os.kill 成功但子进程已退出)。

## Migration Plan

1. 改 `backend.py`(spawn 存句柄 / is_alive 回收+returncode 守护 / stop 清理)
2. 加单测(僵尸判不存活、已退出子进程判不存活、PID 复用不误判、re-adopt 路径不回归)
3. 现有 `test_backend.py` 用例(spawn 命令行、stop CLI、stale PID)须保持绿——注意 spawn mock 现在返回的 `object()` 没有 `poll()`,若 is_alive 在测试里被调到需兼容(用例里 spawn 的 fake 返回需有 `poll`/`returncode`,或 is_alive 对无 `poll` 句柄宽容处理)

无 DB schema 变更,无 migration,接口签名不变。
