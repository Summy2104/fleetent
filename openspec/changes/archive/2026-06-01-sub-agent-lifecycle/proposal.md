## Why

`sub_agent.py` 的 `SubAgentExecutor.run`（行 24-35）当前是 **fire-and-forget**：`asyncio.gather` 并行拉起多个子 agent，调用方（主 agent）调 `run` 即被 `await asyncio.gather(...)` 挂起，只在全部 `_run_one` 结束后一次性拿到 `list[SubAgentResult]`，**在批 gather 结束前无法观察自己子任务的中途状态**——是排队中、正在跑、已完成、还是因异常失败、因卡死阻塞。能在运行中实时查任一子任务状态的，是**运维 / 外部观察者**（另一进程查 `users.db`），而非被挂起的主 agent。`_run_one` 也**没有超时**：`agent_loop.run(...)` 内部某次 LLM 调用或工具执行卡住，对应子任务就会无限期挂起，拖住整批 `gather`，主 agent 既看不到也停不下来。

`docs/capabilities/agent-runtime.md`「sub_agent 生命周期管理」（行 188-190）要求：加 SQLite 状态表，子任务走 `pending → in_progress → done/failed` 状态机，并支持超时检测。同文件待决问题（行 276）「sub_agent 状态表设计：状态机字段、超时时间默认值」长期挂起待认领——这是本 change 必须解决的 **Q2**。

本 change 是波次 3 的 **AR20（sub_agent 生命周期管理）**，在已落地的 `sub-agent` 能力（并行执行 / 独立上下文 / 深度限制 / 权限继承 / trace 关联）之上**加一层生命周期管理**：状态机、超时控制、状态可观测。超时与取消**复用** AR19 已落地的 `cancellation.CancelToken`——「超时 = 带 deadline 的 cancel token」是 `cancellation.py` 已发布的契约，本 change 不另造取消机制；为同时合并「子任务自身 deadline 超时」与「外部 / 父 batch 级取消」两个取消源，本 change 向 `cancellation.py` **增量补全**一个 `parent` 链接原语（纯加法、向后兼容，见 design D3），作为 AR19 的缺口补全由本 change(AR20) 拥有。

## What Changes

- 引入**子 agent 生命周期状态机**：每个子任务在创建到结束的全过程被赋予明确状态——`pending`（已登记未启动）→ `running`（执行中）→ 终态之一 `succeeded` / `failed` / `timed_out` / `cancelled`。状态迁移单向、不可逆，非法迁移被拒。
- 引入**生命周期记录**数据结构（建议 `SubAgentLifecycle` dataclass）：承载子任务标识、所属 `parent_session_id`、当前状态、各状态时间戳、错误信息、超时配额等可观测字段。
- 为每个子任务**注入带 deadline 且链接父 token 的 `CancelToken`**（复用并增量补全 `cancellation.py`）：`_run_one` 启动时按超时配额构造 `CancelToken(deadline=now+timeout, parent=batch_token)` 并透传给 `agent_loop.run(...)`——子任务在既有检查点自然 OR 进父状态，零额外延迟、无需轮询看门狗；到点（自身 deadline 已过）子任务以 `timed_out` 终态收束，**不拖住**同批其他子任务；父 / 外部取消经 `parent` 链接传播则使在途子任务进入 `cancelled` 终态。
- **状态可观测**：生命周期记录可被查询（按 `parent_session_id` 列出本批所有子任务及其当前状态/耗时/错误），**运维 / 外部观察者可实时查询在途状态**（另一进程查 `users.db`），**主 agent 在批 gather 结束后查历史**，不再 fire-and-forget。
- **状态持久化**（标准库 `sqlite3`，不用 aiosqlite/ORM）：生命周期记录落 `users.db` 的新表 `sub_agent_runs`，进程重启后历史可查、运维可审计。表结构与超时默认值见 design 的 Q2 决策。
- 在 `SubAgentExecutor` 上接入生命周期：`run` / `_run_one` 在状态迁移点写记录；既有返回值 `list[SubAgentResult]` 语义保持（向后兼容），生命周期为旁路增强。

## Capabilities

### New Capabilities
- `sub-agent-lifecycle`: 在并行子 agent 之上提供生命周期管理——`pending/running/succeeded/failed/timed_out/cancelled` 状态机、基于 `CancelToken` deadline 的子任务超时控制、可观测且可持久化（`sqlite3`）的状态记录，使子任务不再 fire-and-forget。

### Modified Capabilities
<!-- 不 MODIFY 既有 sub-agent 主 spec：并行执行/独立上下文/深度限制/权限继承/trace 关联五条需求行为不变，本 change 仅在其之上旁路新增生命周期层。生命周期为全新能力，以新 capability `sub-agent-lifecycle` 下 ADDED 表达，避免 archive sync 找不到同名既有需求。 -->

### 共享资源引用
- **`users.db` owner = user_store**：本 change 仅向该库**新增** `sub_agent_runs` 表，复用 `user_store._conn` / `agent_store` 既有的标准库 `sqlite3` 连接惯例（CLAUDE.md 数据目录段已登记 `users.db` 多表共处），不新建 db 文件。
- **`cancellation.CancelToken`（AR19，已落地）**：本 change 作为消费方，按已发布契约「超时 = 带 deadline 的 token」构造并透传；并对 `cancellation.py` 做**增量补全**——新增可选 `parent` 链接字段（纯加法、不改既有语义/既有用法），用于把外部 / 父 batch 级取消传播到子任务 token（见 design D3）。该 `parent` 原语增量归本 change(AR20) 拥有。

## Impact

- **代码**：
  - 新增生命周期数据结构与状态机：建议 `src/fleetent/sub_agent_lifecycle.py`（`SubAgentState` 枚举、`SubAgentLifecycle` dataclass、合法迁移校验、`sqlite3` 持久化 + 查询函数；模块级 `DB_PATH` 可 monkeypatch）。
  - 修改 `src/fleetent/cancellation.py`：`CancelToken` 增量加可选 `parent: CancelToken | None = None` 字段，`is_cancelled()` 在「自身 `_cancelled` / 自身 deadline 已过」之外再 OR 上 `parent.is_cancelled()`（`parent` 默认 None，向后兼容，现有用法零影响）。
  - 修改 `src/fleetent/sub_agent.py`：`_run_one` 按超时配额构造 `CancelToken(deadline=..., parent=batch_token)` 并透传 `agent_loop.run(...)`；在 pending→running→终态各点写生命周期记录；`run` 暴露/接受可选超时与外部 cancel token（作为 batch_token 经 `parent` 链接传播），缺省回退默认超时，既有签名向后兼容。
- **配置**：新增子 agent 超时默认值（见 Q2，可经 `Settings` 覆盖），缺省用安全默认值。
- **测试**：新增 `tests/test_sub_agent_lifecycle.py`（状态机合法/非法迁移、超时进入 `timed_out`、`sqlite3` 持久化与按 `parent_session_id` 查询、`DB_PATH` 隔离到 tmp_path）；扩充 `tests/test_sub_agent.py`（子任务超时不拖累同批、外部取消进入 `cancelled`、返回值语义不回归）。LLM 调用按规范 mock，不发真实请求。
- **不影响**：既有 `sub-agent` 五条需求（并行/独立上下文/深度限制/权限继承/trace）行为不变；不传超时与外部 token 时 `SubAgentExecutor` 行为与现状等价；`cancellation.py` 的 `parent` 增量为纯加法（默认 None），既有 `CancelToken` 用法与语义零回归；不引入新依赖（`cancellation` / 标准库 `sqlite3` 均已在用）。

## Dependencies

- **`src/fleetent/sub_agent.py`（已实现）**：本 change 在其 `SubAgentExecutor.run` / `_run_one` 之上构建生命周期层。
- **`src/fleetent/cancellation.py`（AR19，已实现）**：超时与外部取消复用 `CancelToken`（`deadline` / `is_cancelled()` / `cancel()`），「超时 = 带 deadline 的 token」是其已发布契约。AR19 实现已完结不重开；本 change(AR20) 作为消费方对其做**增量补全**——加可选 `parent` 链接字段、`is_cancelled()` OR `parent`（向后兼容），用于合并双取消源（见 design D3），该增量归本 change 拥有。
- **`src/fleetent/termination.py`（AR1，已实现）**：`StopReason.cancelled` 已预留；子任务被取消/超时时 `agent_loop` 经 `CancellationChecker` 以 `cancelled` 收束，本 change 据此映射子任务终态。
- **`src/fleetent/user_store.py` / `agent_store.py`（已实现）**：复用其标准库 `sqlite3` 连接惯例与 `users.db`，新增 `sub_agent_runs` 表。
