## Why

`run_code`（`tools.py`）经 `_exec_or_cancel`（行 148-166）在 Docker 容器内执行代码：用一个轮询循环等 `client.exec(...)`，仅当**外部** cancel token 被取消（AR19 显式 `cancel()` 或 `deadline` 到点）时才 `exec_task.cancel()` 并 `destroy_workspace`（`docker rm -f`）。这里有两个缺口：

1. **没有沙箱自身的执行超时**：`SandboxResources.exec_timeout`（SB4 已承载、已 clamp 到 `[1, 600]`，默认 30s）目前**无人消费**——一段死循环代码若外层未注入带 `deadline` 的 token，会无限占用容器与轮询协程，沙箱自己不会兜底。
2. **终止手段是 `rm -f` 而非 `docker kill` 序列**：`docs/capabilities/sandbox.md`「执行超时与强制终止」明确要求「超时后对容器执行 `docker kill`（先 SIGTERM，5s 后 SIGKILL）强制终止」，给容器内进程一个优雅退出的窗口；当前实现直接 `rm -f`，无 SIGTERM 宽限。

`docs/capabilities/sandbox.md` 规划项「执行超时与强制终止」（行 98-100、验收场景 2，行 113-116）：默认 30s（可配置，最长 600s），超时后 `docker kill`（SIGTERM → 5s → SIGKILL）强制终止，超时作为错误返回、对话可继续。

本 change 让沙箱**消费 SB4 已承载的 `exec_timeout`**，为 `run_code` 的容器内执行加上沙箱侧的硬性时限：超时即对容器执行 `docker kill` 序列强制终止容器内进程，并把超时归一为 `sandbox_timeout` 错误（AR5 已预留该分类码）返回。这是 `run_code` 沙箱内的**容器侧强制终止**特化，与 T2（`tool-timeout`，工具层 await 竞速、不调 `docker kill`）互补。

## What Changes

- 沙箱执行超时机制：`run_code` 在容器内执行代码时，以 `SandboxResources.exec_timeout`（秒）为时限；执行超过该时限即判定为**沙箱执行超时**。
- 复用 AR19 cancel token 契约表达超时，并经 ②(AR20) 补全的 `parent` 链接原语合并双取消源：沙箱侧构造 `child = CancelToken(deadline=now+exec_timeout, parent=external_token)`（`external_token` 即外部注入或默认 token），轮询判定收为单个 `child.is_cancelled()`——它自然 OR 了「沙箱 `exec_timeout` deadline 到点」与「外部 cancel（用户 / 上层 deadline）」，任一先触发即中止。不在轮询里手写 `external.is_cancelled() or now >= deadline`（那是与 ②/⑤ 同一概念的第二套合并机制）。
- 容器侧强制终止：超时（或外部取消）触发后，对容器执行 `docker kill` **序列**——先 `docker kill --signal=SIGTERM`，等待**固定宽限期**（默认 5s，宽限期内不轮询 `docker inspect` 探测）后**无条件** `docker kill --signal=SIGKILL`（对已停容器幂等无害、省一次 CLI 往返）。`SandboxClient` 新增封装该序列的方法（mock `asyncio.create_subprocess_exec` 断言信号序列）。
- 超时作为错误返回：沙箱执行超时归一为 `ErrorCategory.sandbox_timeout`（AR5 已预留、首次被沙箱执行源接入），返回给用户的文本明确指出是「沙箱执行超时」（区别于外部 cancel 的「已取消」）；对话可继续。
- 终止后的容器处理沿用 SB2 既有约定（`docs/capabilities/sandbox.md` 行 100）：本 change 不改 scope→容器保留/销毁策略，仅负责「容器内进程被强制终止」这一硬动作。

## Capabilities

### New Capabilities
- `sandbox-exec-timeout`: `run_code` 容器内执行超过 `exec_timeout`（SB4 承载的配置，默认 30s、最长 600s）即对容器执行 `docker kill`（SIGTERM → 宽限 → SIGKILL）强制终止容器内进程，超时归一为 `sandbox_timeout` 错误返回、对话可继续。

### Modified Capabilities
<!-- 不修改既有 spec。本 change 引入的「沙箱执行超时强制终止」为新增治理能力，落在新 capability `sandbox-exec-timeout` 下以 ADDED 表达；既有 sandbox-client 主 spec 为 microsandbox 历史版本，无对应需求，不以 MODIFIED 表达（否则 archive sync 找不到同名既有需求）。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/sandbox_client.py`：新增 `docker kill` 序列封装方法（SIGTERM → 宽限期 → SIGKILL），宽限期为可注入的模块级常量。
  - 修改 `src/fleetent/tools.py` 的 `_exec_or_cancel`（及 `run_code` 调用处）：消费 `exec_timeout` 构造 `child = CancelToken(deadline=now+exec_timeout, parent=external_token)`，轮询判定收为单个 `child.is_cancelled()`（经 `parent` 链接合并沙箱 deadline 与外部 token，复用 ②(AR20) 原语，不手写 OR）；触发后按 `child.deadline` 是否已过区分超时 / 取消；超时改走 `docker kill` 序列而非直接 `rm -f`；超时归一为 `sandbox_timeout` 错误文本返回。
  - 复用 `src/fleetent/error_classifier.py` 的 `ErrorCategory.sandbox_timeout` 与 `CLASSIFICATION_TABLE` 既有条目（不改分类表结构），令该预留码经沙箱执行源首次可达。
- **测试**：扩充 `tests/test_sandbox_client.py` 断言 `docker kill` 信号序列；扩充 `tests/test_tools.py`（或新增沙箱执行超时用例）断言超时触发 `docker kill`、归类 `sandbox_timeout`、错误文本。Docker CLI（`asyncio.create_subprocess_exec`）全部 mock，不跑真容器；超时用注入极短 `exec_timeout` / 受控慢 stub，不依赖墙钟长等待；隔离 `tmp_path`/`monkeypatch`。
- **不影响**：SB4 资源配置加载（仅消费其 `exec_timeout` 字段）、SB2 scope→容器保留/销毁策略、T2 工具层通用超时（边界见 design）、AR5 分类表结构。不引入新依赖。

## Dependencies

- **`src/fleetent/sandbox_client.py`**（已实现）：`exec` 经 `docker exec` 跑代码、`destroy_workspace` 经 `docker rm -f`、统一封装 Docker CLI；本 change 在其上新增 `docker kill` 序列方法。
- **`src/fleetent/sandbox_config.py`**（SB4 已实现）：`SandboxResources.exec_timeout`（秒，已 clamp `[1, 600]`，默认 30）——本 change **消费**该字段作为执行时限，不重复加载/校验。
- **`src/fleetent/cancellation.py`**（AR19 已实现 + ② 增量补全）：`CancelToken(deadline=...)` / `is_cancelled()` 契约——沙箱侧 `exec_timeout` 以同一 deadline 语义表达。本 change **复用 ②(sub-agent-lifecycle, AR20) 增量补全到 `cancellation.py` 的 `parent` 链接原语**（`CancelToken` 可选 `parent` 字段，`is_cancelled()` OR `parent.is_cancelled()`，纯加法、向后兼容）合并沙箱 deadline 与外部 / 父 token，与 ⑤(tool-timeout) 一致。该 `parent` 原语现有 ②/⑤/⑫ 三个消费者，归属仍为 ② 拥有增量、本 change 仅消费；归档顺序上 ② 对 `cancellation.py` 的 `parent` 增量须先就位。
- **兄弟 change `tool-timeout`（T2，工具层通用超时）**（边界依赖）：T2 在 `_safe_dispatch` 的 await 层竞速 + cancel token，归类 `tool_timeout`，**不调 `docker kill`**；SB7 是 `run_code` 沙箱内的容器侧强制终止特化，归类 `sandbox_timeout`。两者源自 AR19 同一 token 契约、层级与中止手段不同，design 钉死边界。
