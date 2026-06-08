## Why

`agent.yaml` 已声明 `permission_gate_medium_timeout_seconds` / `permission_gate_high_timeout_seconds`
两个字段，但从未被读取并传给实际的 gate 实例；同时缺少 `permission_gate_enabled` 开关，导致无法
通过配置禁用审批门控——唯一的绕过方式是手改工具 risk_level 或改用无 `reply_func` 的入口。

## What Changes

- **新增** `AgentFile.permission_gate_enabled: bool = True` 字段，控制是否启用 medium/high
  风险工具的审批拦截
- **接入** 已有的 `permission_gate_medium_timeout_seconds`（默认 300）和
  `permission_gate_high_timeout_seconds`（默认 3600）字段，使其实际生效
- **`loop.run()`** 新增 `permission_gate_enabled` 参数，向内传递给 `_plan_tool_slots()`；
  当 `False` 时跳过 gate，工具直接进入执行队列
- **`normalizer.py`** 和 **`agent_app.py`** 的 `/chat` 路由从 agent 配置读取开关和超时值，
  传入 `loop.run()`；同时用 agent 配置的超时创建 per-call `PermissionGate` 替代全局单例
- **`agent.yaml.example`** 补充 `permission_gate_enabled` 字段注释

## Capabilities

### New Capabilities

- `permission-gate-config`：agent.yaml 可配置 permission gate 开关（enabled/disabled）及
  medium/high 风险工具的审批超时时长

### Modified Capabilities

- `permission-gate`：补充"gate 可按 agent 配置禁用"和"超时从 agent.yaml 读取"两条要求

## Impact

- `src/fleetent/agent_config.py`：新增 `permission_gate_enabled` 字段
- `src/fleetent/runtime/loop.py`：`run()` 和 `_plan_tool_slots()` 新增 gate 开关参数
- `src/fleetent/im_gateway/normalizer.py`：传入开关和 per-call gate 实例
- `src/fleetent/runtime/agent_app.py`：`/chat` 路由同上
- `agents/default/agent.yaml.example`：示例补充
- 测试：`tests/unit/test_permission_gate_config.py`（新增）
