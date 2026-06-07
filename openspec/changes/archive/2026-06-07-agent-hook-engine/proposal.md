## Why

引入 hook 扩展体系的**引擎地基 + 首个钩子点 `pre_tool_use`**（完整设计见 `docs/hooks-system-design-decisions.md`）。企业 on-prem 客户需在**不改内核**的前提下，于工具调用前做合规拦截/改参，并为后续钩子点（P2–P4）一次性确立接口契约。

## What Changes

- **新增 `runtime/hooks.py`（引擎）**：`@hook(event)` 注册装饰器 + `HookContext`/`HookResult` + `dispatch(event, ctx, *, timeout, strict)`（按注册序、决策点 first-deny-wins、变换链、**异常隔离 + 超时**）+ `has_hooks(event)` + `reset()`。纯进程内 Python。
- **配置**：`AgentFile` + `GovernanceConfig` + `_governance_from_file` 加 `hooks_enabled`（默认 `False`）/ `hooks_decision_failure`（`open`|`strict`，默认 `open`）/ `hooks_timeout_seconds`（默认 5）。
- **`pre_tool_use` 钩子点**：在 `loop._plan_run_slots` 与 `run_stream` 的工具准入处，当启用且有注册 hook 时 `dispatch` 并**与 `agent_policy`/`permission_gate` 组合**：`deny`→跳过分发并把 reason 反馈模型；`ask`→强制走 permission_gate；`modified_args`→改写入参；`proceed`→继续。
- **加载**：`@hook` 定义在 agent-local 插件包内，随 `plugin_loader` import 该包时**副作用注册**（与 `@tool` 同机制，无需改 plugin_loader）。

## Capabilities

### New Capabilities

- `agent-hooks-engine`: hook 注册/派发引擎——契约、按序、隔离、超时、默认关闭、agent-local 加载。
- `agent-hook-pre-tool-use`: 工具调用前的决策/改参钩子点，与既有准入组合。

### Modified Capabilities

（无）

## Impact

- **修改文件**：`src/fleetent/runtime/loop.py`（pre_tool_use 集成）、`src/fleetent/agent_config.py`、`src/fleetent/runtime/snapshot.py`、`agents/default/agent.yaml.example`；**新增** `src/fleetent/runtime/hooks.py`。
- **解耦合规**：纯 `runtime/`、进程内 Python、永不 shell、agent-local、零 platform/DB；`hooks_enabled=False`（默认）时零注册派发、**字节级行为不变**。
- 引擎 registry 为可 `reset()`/monkeypatch 的 module-level 状态（守红线）。
