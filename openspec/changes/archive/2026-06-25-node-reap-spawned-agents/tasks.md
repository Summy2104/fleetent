## 1. is_alive 判僵尸/已退出子进程为不存活

- [x] 1.1 测试：构造一个 spawn 后句柄 `poll()` 返回退出码（`returncode` 非 None）、但 `os.kill(pid,0)` 仍成功的场景，断言 `is_alive` 返回 `None`（红）
- [x] 1.2 实现：`LocalProcessBackend.spawn` 保留 `Popen` 句柄到 `self._procs[agent_name]`；`is_alive` 对有句柄的 agent 先 `proc.poll()`，若 `returncode is not None` 返回 `None`，否则走既有 PID 文件 + `os.kill` 路径
- [x] 1.3 测试通过（绿）

## 2. PID 复用不误判

- [x] 2.1 测试：句柄已退出（returncode 置）、原 PID 被复用使 `os.kill(pid,0)` 成功，断言 `is_alive` 返回 `None`（红）
- [x] 2.2 实现：确保 `returncode` 判定优先于 `os.kill`（1.2 已覆盖则确认此测试绿）
- [x] 2.3 测试通过（绿）

## 3. stop 回收句柄

- [x] 3.1 测试：stop 后 `self._procs` 中该 agent 句柄被清理（红）
- [x] 3.2 实现：`stop` 在 CLI 调用后 `poll()` 回收并从 `self._procs` 移除该 agent；回收放独立 finally，不吞 `fleetent agent stop` 的异常（`check=True` 仍 raise）
- [x] 3.3 测试通过（绿）

## 4. 不回归既有行为

- [x] 4.1 测试：re-adopt 路径——无句柄（`self._procs` 空）时，stale PID（`os.kill` 抛 `ProcessLookupError`）仍判 `None`；活进程（`os.kill` 成功、无句柄）仍判返回 pid（红→绿，或确认既有用例不破）
- [x] 4.2 调整既有 `test_backend.py`：`spawn` 的 fake `Popen` 返回对象需具备 `poll()`/`returncode`（或确保 is_alive 对无 `poll` 句柄宽容），使 `test_local_backend_spawn_*` 与 `is_alive` 用例并存不冲突
- [x] 4.3 运行 `uv run pytest tests/unit/node/test_backend.py -q` 全绿

## 5. 集成验证

- [x] 5.1 运行 `make test-pr`，对照 main 基线无新增失败
- [x] 5.2 运行 `make test-unit-ci`（含 76% 覆盖率门禁），无新增失败
- [x] 5.3 运行 `uv run pytest tests/unit/node tests/integration/test_node_reconcile_resilience.py -q`，确认 node 侧无回归
