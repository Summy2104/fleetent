## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `SubAgentExecutor.run`（sub_agent.py 行 24-35）与 `_run_one`（行 37-59）现签名与 `SubAgentResult` 字段；确认生命周期为旁路增强、不改批返回契约，不破坏既有 `tests/test_sub_agent.py`
- [x] 1.2 核实 `cancellation.CancelToken` 契约：`CancelToken(deadline=time.monotonic()+timeout)`、`is_cancelled()`（显式取消或 deadline 已过为真）、`cancel()`；确认 `agent_loop.run(...)` 已接受 `cancel_token` 参数可透传（AR19 已落地）
- [x] 1.3 核实标准库 `sqlite3` 连接惯例：`agent_store` 从 `user_store` re-export `DB_PATH`（`# noqa` 供 monkeypatch）、复用 `_conn()` 写 SQL、`users.db` 多表共处；确认本 change 仅向 `users.db` 新增 `sub_agent_runs` 表，不新建 db 文件
- [x] 1.4 核实 `Settings` 既有 env-first 风格（如 `agent_max_turns`）与 `termination.resolve_limits` 的「call param > config > default」优先级范式，作为超时默认值（300s）解析依据

## 2. 状态机与数据结构（sub_agent_lifecycle.py）

- [x] 2.1 Write failing tests：`SubAgentState`（StrEnum）含 `pending`/`running`/`succeeded`/`failed`/`timed_out`/`cancelled`；`SubAgentLifecycle` dataclass 字段为 `run_id`/`parent_session_id`/`name`/`state`/`timeout_seconds`/`created_at`/`started_at`/`ended_at`/`error`，默认 state 为 `pending`。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement `SubAgentState` 与 `SubAgentLifecycle`（模块结构 import → 常量 → 数据类 → 函数），看到绿

## 3. 状态迁移校验（sub_agent_lifecycle.py）

- [x] 3.1 Write failing tests：合法迁移 `pending→running`、`running→{succeeded,failed,timed_out,cancelled}`、`pending→cancelled` 通过；非法迁移（如 `succeeded→running`、`pending→succeeded`、终态→任意）抛 `ValueError` 不静默吞。看到红
- [x] 3.2 Implement 迁移校验函数（合法迁移表 + 非法 raise `ValueError` 并 log），看到绿

## 4. sqlite3 持久化与查询（sub_agent_lifecycle.py）

- [x] 4.1 Write failing tests：`init_db` 建 `sub_agent_runs` 表幂等（重复建不报错、不丢数据）；写入记录后重开连接按 `run_id` 原样读回；`monkeypatch DB_PATH` 到 tmp_path。看到红
- [x] 4.2 Implement 建表（`CREATE TABLE/INDEX IF NOT EXISTS`）+ 写入/更新记录函数（标准库 `sqlite3`，复用 `_conn`，`DB_PATH` 从 `user_store` re-export 可 monkeypatch），看到绿
- [x] 4.3 Write failing tests：按 `parent_session_id` 查询返回该批所有子任务及其最新 `state`/时间戳/`error`；迁移到终态后查询反映终态与 `ended_at`。看到红
- [x] 4.4 Implement 按 `parent_session_id` 查询函数，看到绿

## 5. 超时配额解析（sub_agent_lifecycle.py / config）

- [x] 5.1 Write failing tests：超时默认 `300`；`Settings.sub_agent_timeout_seconds` 覆盖默认；调用参数覆盖配置（优先级 call > config > default）。看到红
- [x] 5.2 Implement 超时解析（模块常量 `SUB_AGENT_TIMEOUT_SECONDS=300` + `Settings` 字段 + 解析函数，照 `resolve_limits` 范式），看到绿

## 6. cancellation.py `parent` 链接原语（增量补全 AR19）

- [x] 6.1 Write failing tests：`CancelToken(deadline=..., parent=p)` 当 `p.cancel()` 后 `child.is_cancelled()` 为真（父取消经 `parent` 传播）；`parent=None`（默认）时 `is_cancelled()` 行为与现状等价（仅自身 `_cancelled` / 自身 deadline）不回归；父未取消时子仅按自身 deadline / `_cancelled` 判定。看到红
- [x] 6.2 Implement：`CancelToken` 增量加可选 `parent: CancelToken | None = None` 字段，`is_cancelled()` 在自身判定外 OR 上 `parent.is_cancelled()`（纯加法、不改既有分支语义），看到绿

## 7. 生命周期接入执行器（sub_agent.py）

- [x] 7.1 Write failing tests：`_run_one` 启动前以超时配额构造 `CancelToken(deadline=..., parent=batch_token)` 透传 `agent_loop.run(..., cancel_token=...)`，并在 pending→running→终态各点写生命周期记录（mock `agent_loop.run`、`DB_PATH` 隔离 tmp_path、用短超时）。看到红
- [x] 7.2 Implement `_run_one` 接入生命周期写入与带 `parent` 链接的 token 透传，看到绿
- [x] 7.3 Write failing tests：单子任务超时进入 `timed_out` 且同批其余正常完成为 `succeeded`（per-task token 独立，不拖累 `gather`）。看到红
- [x] 7.4 Implement 超时收束逻辑（据子任务 token 自身 `deadline` 已过判 `timed_out`），看到绿
- [x] 7.5 Write failing tests：父 / 外部 cancel token（`batch_token`）在 deadline 前 `cancel()` → 经子任务 token 的 `parent` 链接传播，受影响在途子任务记 `cancelled`（区分于 `timed_out`）；pending 阶段被取消 → `pending→cancelled` 且 `started_at` 为空。看到红
- [x] 7.6 Implement 经 `parent=batch_token` 链接的外部取消传播与终态区分（子任务 token 自身 deadline 已过记 `timed_out`，否则 `cancelled`），看到绿
- [x] 7.7 Write failing test：不传超时与外部 token 时 `SubAgentExecutor.run` 返回 `list[SubAgentResult]` 与现状等价（既有 `test_sub_agent.py` 不回归），生命周期为旁路。看到红/绿确认兼容

## 8. 收尾

- [x] 8.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [x] 8.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [x] 8.3 `uv run mypy src` 无新增错误
