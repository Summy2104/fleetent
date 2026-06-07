## 1. steering 引擎（TDD）

- [x] 1.1 写失败测试（`tests/unit/test_steering.py`，用 `steering.reset()` 隔离）：`register_run` 期间 `is_running` 为真、退出后为假且 handle 不泄漏；`steer` 入队返回 True、无活跃 run 返回 False、邮箱满返回 False；`drain` 取出全部并清空；`interrupt` 触发 token.cancel()。看红
- [x] 1.2 实现 `runtime/steering.py`（`RunHandle` + module dict + `register_run`/`is_running`/`steer`/`interrupt`/`drain`/`reset`）。看绿

## 2. loop 轮间消费（TDD）

- [x] 2.1 写失败测试（`tests/unit`）：`_drain_steering(session_id, messages)` 把登记 handle 的 pending 作为 user 消息追加；无 session / 无 handle 时 no-op 不改 messages。看红
- [x] 2.2 实现 `loop._drain_steering` + 在 `run()`/`run_stream()` 主循环压缩后、sanitize 前调用。看绿

## 3. normalizer 分派 + 配置（TDD）

- [x] 3.1 写失败测试（`tests/unit`）：`AgentFile`/`GovernanceConfig` 含 `steering_mode`(默认 steer)/`steering_max_pending`(默认 8)，`_governance_from_file` 映射；（route 分派以 steering 引擎单测覆盖核心，normalizer 改造以现有 normalizer 测试不回归为准）。看红
- [x] 3.2 实现：`AgentFile` + `GovernanceConfig` + `_governance_from_file` 加字段；`normalizer.route()` 抢锁前 `is_running` 分派（steer/interrupt/queue）+ `register_run` 包裹 run + 传 `cancel_token` + 内容只构建一次。看绿

## 4. 收尾

- [x] 4.1 `uv run ruff format`（改动文件）、`ruff check`（改动）、`mypy`（改动源文件）、`uv run python scripts/check_test_layers.py`、全量 `uv run pytest -x -q`
- [x] 4.2 `openspec validate agent-input-steering --strict` 通过
