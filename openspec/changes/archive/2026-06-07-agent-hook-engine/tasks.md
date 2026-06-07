## 1. 引擎 runtime/hooks.py（TDD）

- [x] 1.1 写失败测试（`tests/unit/test_hooks_engine.py`，`hooks.reset()` 隔离）：`@hook` 注册 + `dispatch` 按序；决策点 first-deny-wins；变换点链式（modified_args/content 回灌）；hook 异常被隔离不抛；超时跳过；`strict` 失败=deny / `open` 失败=放行；`has_hooks`；`reset`。看红
- [x] 1.2 实现 `runtime/hooks.py`（`HookContext`/`HookResult`/`hook`/`_registry`/`dispatch`/`has_hooks`/`reset`，sync+async 兼容、`asyncio.wait_for` 超时、异常隔离）。看绿

## 2. 配置（TDD）

- [x] 2.1 写失败测试（`tests/unit`）：`AgentFile`/`GovernanceConfig` 含 `hooks_enabled`(False)/`hooks_decision_failure`("open")/`hooks_timeout_seconds`(5.0)，`_governance_from_file` 映射。看红
- [x] 2.2 实现 `AgentFile` + `GovernanceConfig` + `_governance_from_file` 三字段。看绿

## 3. pre_tool_use 集成（TDD）

- [x] 3.1 写失败测试（`tests/unit/test_agent_loop.py` 或新文件，复用 mock_client + 注册 pre_tool_use hook + 启用 hooks via governance）：`deny`→工具不分发、reason 反馈、序列合法；`modified_args`→以改写入参执行；`ask`→低风险也走审批；`hooks_enabled=False` 或无注册→工具准入零变化。看红
- [x] 3.2 实现：`_plan_run_slots` 与 `run_stream` plan 在准入处 `dispatch("pre_tool_use")` 并组合（deny/ask/modified_args/proceed）；`has_hooks`+`hooks_enabled` 双门；run_stream 的 `ask` 退化为 deny+提示。看绿

## 4. 加载接线 + 收尾

- [x] 4.1 确认 run/run_stream（IM/server）路径触发插件加载使 `@hook` 注册；缺则补 best-effort 加载。`agents/default/agent.yaml.example` 补 hooks_* 字段。
- [x] 4.2 `uv run ruff format`（改动）、`ruff check`（改动）、`mypy`（改动源）、`uv run python scripts/check_test_layers.py`、全量 `uv run pytest -x -q`；`openspec validate agent-hook-engine --strict`。
