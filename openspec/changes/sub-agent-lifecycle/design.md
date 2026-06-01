## Context

`SubAgentExecutor.run`（sub_agent.py 行 24-35）用 `asyncio.gather` 并行跑 `_run_one`；`_run_one`（行 37-59）对单个 task 调 `agent_loop.run(messages=[...], user_id=..., is_sub_agent=True)`，成功返回 `SubAgentResult(result=...)`，异常被 `except Exception` 捕获返回 `SubAgentResult(error=str(exc))`。问题有二：①**主 agent 无法观察在途状态**——主 agent 调 `run` 即被 `await asyncio.gather(...)` 挂起，只能在整批 `gather` 完成后拿结果，批结束前看不到任一子任务是排队/运行/已结束；运行中能实时查的是**运维 / 外部观察者**（另一进程查 `users.db`）；②**无超时**——`agent_loop.run(...)` 内部卡住则该子任务无限挂起，并拖住整批 `gather`。

AR19 `cancellation.py` 已落地并对外发布契约：`CancelToken(deadline=time.monotonic()+timeout)`、`is_cancelled()`（显式取消 或 deadline 已过均为真）、`cancel()`；`CancellationChecker` 已把 token 接入 AR1 `termination` 框架，子循环到点以 `StopReason.cancelled` 优雅停止。本 change 作为**消费方**复用该契约，不另造取消/超时机制；但 `CancelToken` 当前**无组合能力**，无法让一个子任务 token 同时反映「自身 deadline」与「父 / 外部取消」两个源——本 change 对 `cancellation.py` 做一处**增量补全**（加可选 `parent` 链接，见 D3），AR19 实现本身不重开。

`agent_store.py` 已示范标准库 `sqlite3` 连接惯例：从 `user_store` re-export `DB_PATH`（`# noqa` 注释标明供测试 monkeypatch）、复用 `_conn()` 上下文管理器写 SQL，`users.db` 多表共处（CLAUDE.md 数据目录段已登记）。本 change 沿用此惯例，向 `users.db` 新增 `sub_agent_runs` 表，不用 aiosqlite、不用 ORM。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM（标准库 `sqlite3` 直写 SQL）；禁止全局可变状态（`DB_PATH` / 默认超时常量可 monkeypatch）；新模块 import → 常量 → 数据类 → 函数；mypy strict 全注解；行长 100；TDD Hard Gate；测试 mock LLM、`DB_PATH` 隔离到 tmp_path、用短超时（不跑真实长等待）；不吞异常（迁移/持久化错误要 log 或 re-raise）。

**既有 spec 归属**：现有 `openspec/specs/sub-agent/spec.md` 的五条需求（并行执行 / 独立上下文 / 深度限制 / 权限继承 / trace 关联）行为本 change 不动。生命周期为旁路新增层，全部以新 capability `sub-agent-lifecycle` 下的 ADDED 表达，不对 sub-agent 主 spec 做 MODIFIED（否则 archive sync 找不到同名既有需求）。

## Goals / Non-Goals

**Goals:**
- 定义子 agent 生命周期**状态机**：`pending → running → {succeeded | failed | timed_out | cancelled}`，单向不可逆，非法迁移被拒。
- 定义生命周期**记录**数据结构与 `sqlite3` 持久化表（`sub_agent_runs`），可按 `parent_session_id` 查询当前状态/耗时/错误——**状态可观测**。
- 子任务**超时控制**：每个 `_run_one` 注入带 deadline 的 `CancelToken`（复用 AR19），到点该子任务以 `timed_out` 收束且**不拖累同批**其余子任务。
- 在 design 钉死 **Q2**：①状态机状态与字段；②超时默认值（具体数 + 可配置说明）。给出明确决策，不留 OQ。

**Non-Goals:**
- 不实现失败子任务的**自动重试**（docs 列为后续，本 change 只到 `failed` 终态可观测，重试由上层决策）。
- 向 `cancellation.py` **增量添加 `parent` 链接原语**（纯加法、不改既有语义 / 既有用法），不另造取消机制；不改 `termination.py`（仅消费其已发布契约）。
- 不改 `sub-agent` 五条既有需求行为；不改深度限制（仍最大深度 1）。
- 不引入新依赖；不暴露新 HTTP 端点（可观测先以 `sqlite3` 查询函数提供，CLI/HTTP 暴露留后续）。

## Decisions

### D1（解决 Q2 ①状态机字段 / ②超时默认值）：`sub_agent_runs` 状态表设计

**① 状态机字段。** 新增 `src/fleetent/sub_agent_lifecycle.py`：

- `SubAgentState`（`StrEnum`，str 值便于 JSONL/SQLite 序列化，与 `termination.StopReason` 一致风格）：
  - `pending` —— 已登记、未启动。
  - `running` —— `agent_loop.run(...)` 执行中。
  - `succeeded` —— 终态：正常完成。
  - `failed` —— 终态：`agent_loop` 抛异常（非取消/超时）。
  - `timed_out` —— 终态：本子任务 deadline 已过（token 因 deadline 取消）。
  - `cancelled` —— 终态：外部 cancel token 显式取消（非 deadline）。
- 合法迁移（单向、终态不可再迁移）：
  `pending → running`；`running → succeeded`；`running → failed`；`running → timed_out`；`running → cancelled`；以及 `pending → cancelled`（启动前即被外部取消）。其余一律非法，迁移函数对非法迁移 raise `ValueError`（不静默吞）。
  > `timed_out` 与 `cancelled` **区分**：deadline 触发 → `timed_out`；外部显式 `cancel()` 触发 → `cancelled`。`CancelToken.is_cancelled()` 合并二者，故终态判定时检查 `token.deadline` 是否已过来区分（deadline 已过记 `timed_out`，否则记 `cancelled`）。

- `SubAgentLifecycle`（dataclass）—— 对应 `sub_agent_runs` 一行，字段：
  | 字段 | 类型 | 说明 |
  | --- | --- | --- |
  | `run_id` | `str` | 子任务运行唯一标识（uuid4 hex），主键。 |
  | `parent_session_id` | `str` | 所属父 session，可观测查询的过滤键（建索引）。 |
  | `name` | `str` | 子任务名（来自 `task["name"]`）。 |
  | `state` | `SubAgentState` | 当前状态。 |
  | `timeout_seconds` | `int` | 本次生效的超时配额（见 ②）。 |
  | `created_at` | `str` | 登记（pending）时间，ISO8601 UTC。 |
  | `started_at` | `str \| None` | 进入 running 的时间，未启动为 None。 |
  | `ended_at` | `str \| None` | 进入终态的时间，未结束为 None。 |
  | `error` | `str \| None` | failed 时的错误摘要；非 failed 为 None。 |

  对应 SQL（标准库 `sqlite3`，TEXT 存枚举/时间，`CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS sub_agent_runs(parent_session_id)`）：
  ```sql
  CREATE TABLE IF NOT EXISTS sub_agent_runs (
    run_id            TEXT PRIMARY KEY,
    parent_session_id TEXT NOT NULL,
    name              TEXT NOT NULL,
    state             TEXT NOT NULL,
    timeout_seconds   INTEGER NOT NULL,
    created_at        TEXT NOT NULL,
    started_at        TEXT,
    ended_at          TEXT,
    error             TEXT
  );
  CREATE INDEX IF NOT EXISTS idx_sub_agent_runs_parent
    ON sub_agent_runs(parent_session_id);
  ```
  模块级 `DB_PATH` 从 `user_store` re-export（`# noqa` 供测试 monkeypatch），复用 `_conn()`，与 `agent_store` 完全一致。`耗时` 不单列存储——由 `ended_at - started_at` 在查询/展示时算出，避免冗余可变字段。

**② 超时默认值。** 子 agent 单任务超时默认 **`SUB_AGENT_TIMEOUT_SECONDS = 300`（5 分钟）**，**可经 `Settings` 覆盖**（新增 `sub_agent_timeout_seconds: int = 300`，env-first，与既有 `agent_max_turns` 等同款风格）。优先级：`run()` 调用参数 > `Settings` > 模块默认常量 `300`，解析逻辑照 `termination.resolve_limits` 范式（call param > config/Settings > default）。

- **为何取 300s**：子 agent 是「主 agent 派生的一个完整子任务」（独立上下文跑一轮 `agent_loop`，可能多轮 LLM + 工具调用），比单次工具调用（波次 3 工具超时量级为数十秒）耗时长一个量级；该值是一道**与主任务预算正交的 wall-clock 守卫**（不暗示强制小于主预算，两者各自独立约束），5 分钟在「容纳一个实质子任务」与「卡死时尽快暴露」间取平衡，且对齐 docs 对子任务「超时检测」的诉求。取整 300 便于运维记忆与覆盖。
- 超时落地：`_run_one` 启动前 `deadline = time.monotonic() + timeout_seconds`，构造 `CancelToken(deadline=deadline, parent=batch_token)`（`parent` 为本批的外部 / 父级 token，经 D3 链接合并双取消源）透传 `agent_loop.run(..., cancel_token=token)`（AR19 已支持该参数）。子循环到点经 `CancellationChecker` 以 `StopReason.cancelled` 优雅停止；`_run_one` 据 `token.deadline` 已过判定记 `timed_out`（否则为父 / 外部触发，记 `cancelled`），单个子任务收束**不影响** `gather` 中其余协程。

**为何独立模块**：状态机 + 持久化是新职责，独立 `sub_agent_lifecycle.py` 保持 `sub_agent.py` 聚焦「并行编排」；模块结构 import → 常量（`DB_PATH` / 默认超时）→ 数据类（枚举 + dataclass）→ 函数（迁移校验 / 写入 / 查询），符合 CLAUDE.md 新模块规范。**Alternatives**：①把状态字段塞进既有 `SubAgentResult`——被否，`SubAgentResult` 是「批结束后的返回值」，承载不了运行中可观测与持久化；②用内存 dict 存状态——被否，进程重启即丢、运维不可审计，docs 明确要求 SQLite 表。

### D2：生命周期接入 `SubAgentExecutor`，返回值向后兼容

`SubAgentExecutor.run(tasks, parent_user_id, parent_agent_id, parent_session_id, *, timeout_seconds=None, cancel_token=None)`：新增两个**可选**关键字参数，缺省回退默认超时、外部 token（`cancel_token`，即本批的 `batch_token`）缺省为永不取消的默认 token——不传时与现状等价。`_run_one` 在 pending（登记）→ running（启动前）→ 终态（结束）各点调用生命周期写函数；既有 `list[SubAgentResult]` 返回值语义与字段不变，生命周期为**旁路增强**，调用方无需改动即可受益于超时保护（默认 300s）。
**为何**：向后兼容是硬约束（既有 `test_sub_agent.py` 不能回归）；生命周期记录与超时为旁路叠加，不改变批返回契约。
**Trade-off**：可观测目前以 `sqlite3` 查询函数提供——**运维 / 外部观察者可实时查询在途状态**（另一进程查 `users.db`），**主 agent 在批 `gather` 结束后查历史**（被挂起期间无法观察自己子任务的中途状态）；未直接暴露 HTTP/CLI，留作后续，本 change 先把可查询的持久化层建稳。

### D3：双取消源经 `cancellation.py` `parent` 链接合并

子任务必须同时响应两个取消源：①**自身 per-task deadline 超时**；②**外部 / 父 batch 级取消**。`CancelToken` 是协作轮询式——`is_cancelled()` 在 `agent_loop` 的检查点被轮询，父取消不会异常注入子任务，子任务只能轮询一个能反映父状态的 token。而现有 `CancelToken` **无组合能力**，一个 token 无法同时携带这两个源。

**决策（方案 A）：向 `cancellation.py` 的 `CancelToken` 增量添加可选 `parent: CancelToken | None = None` 字段**，`is_cancelled()` 在「自身 `_cancelled` / 自身 deadline 已过」之外再 **OR 上 `parent.is_cancelled()`**。纯加法、`parent` 默认 None、现有所有 `CancelToken` 用法零影响。子任务用：
```python
child = CancelToken(deadline=now + timeout, parent=batch_token)
agent_loop.run(..., cancel_token=child)
```
父 batch token 一旦取消，子任务在既有检查点轮询 `child.is_cancelled()` 时自然 OR 进父状态——**零额外延迟、无需轮询看门狗**。

**timed_out vs cancelled 区分（合并后）**：`child.is_cancelled()` 为真后——若子任务**自身 deadline 已过** → `timed_out`；否则（父 / 外部触发）→ `cancelled`。

**归属**：该 `parent` 原语增量归本 change(AR20)。AR19（cancellation-propagation）已实现完结、不重开；本 change 作为消费方补上这个 AR19 缺口——这是对 AR19`cancellation.py` 的**增量补全**，非新造取消机制。

**Alternatives**：
- ① 在 `SubAgentExecutor` 层起一个轮询看门狗，监视 `batch_token` 并在父取消时调子 `token.cancel()`——被否：等于在 `sub_agent` 层**重造取消传播**，有轮询延迟、丑，且把本属 `cancellation.py` 的组合语义散落到消费方。
- ② 修改 `is_cancelled()` 的逻辑分支（如改取消判定语义）——被否：本 change 只做**纯加法**（新增可选字段 + 一处 OR），不动既有判定分支，保证现有用法零回归。

## Risks / Trade-offs

- [非法状态迁移被误触发（如对已 succeeded 的记录再迁移）] → 迁移函数对非法迁移 raise `ValueError` 并 log，不静默吞；spec 用 scenario 覆盖「非法迁移被拒」。
- [`timed_out` 与 `cancelled` 混淆（二者都经 token 取消）] → 终态判定据 `token.deadline` 是否已过区分（D1 ①），spec 分别给 scenario。
- [单子任务超时拖累整批] → 超时以 per-task `CancelToken(deadline)` 实现，`gather` 中各协程独立收束；spec 给「一个子任务超时、其余正常完成」scenario。
- [持久化写失败影响主流程] → 生命周期写为旁路，写失败 log 后不阻断子任务执行结果返回（不吞——记录 error 级日志）；`DB_PATH` 测试隔离到 tmp_path。
- [默认 300s 不适配某些部署] → 经 `Settings.sub_agent_timeout_seconds` 与 `run()` 参数覆盖（D1 ②）。

## Open Questions

无。Q2（状态机字段 + 超时默认值）已在 D1 钉死：状态 `pending/running/succeeded/failed/timed_out/cancelled`，表字段见 D1 ① 表，超时默认 `300s` 可经 `Settings` 覆盖。失败重试与状态的 HTTP/CLI 暴露明确划为 Non-Goals / 后续，不属本 change 待决项。
