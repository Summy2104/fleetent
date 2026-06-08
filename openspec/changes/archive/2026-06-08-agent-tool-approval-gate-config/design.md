## Context

`agent.yaml` 已有 `permission_gate_medium_timeout_seconds` / `permission_gate_high_timeout_seconds`
两个字段（`AgentFile` schema 第 272-273 行），但两者在整个代码库中从未被读取——`_default_gate` 是
模块级单例，在 `permission_gate.py:119` 以硬编码默认值构造，不受任何 agent 配置影响。loop 的
`_plan_tool_slots()` 直接引用该单例，且没有开关能跳过 gate 逻辑。

唯一的绕过方式是：使用 `run_stream()`（无 `reply_func`），或手改工具 `risk_level`——均不可配置。

## Goals / Non-Goals

**Goals:**
- `agent.yaml` 新增 `permission_gate_enabled: bool` 开关，`false` 时 medium/high 工具跳过审批直接执行
- 接入已有的 `permission_gate_medium_timeout_seconds` / `permission_gate_high_timeout_seconds`，使其真正生效
- 最小侵入：不改变 `PermissionGate` 类内部，不引入新的全局状态

**Non-Goals:**
- 按工具粒度配置不同 risk level（`allowed_tools` 已覆盖访问控制，不在此范围）
- 改变 `run_stream` 无 gate 的现有行为
- UI 配置入口

## Decisions

### D1：参数透传而非全局重配

**选择**：在 `loop.run()` 新增 `permission_gate_enabled: bool = True` 参数，向下传给
`_plan_tool_slots()`；创建 per-call `PermissionGate(medium_timeout, high_timeout)` 实例替代
`_default_gate`。

**否决**：启动时重配全局 `_default_gate`——多 agent 并发时产生竞争，且违反"agent 运行时不共享
platform 全局状态"的架构契约。

**否决**：在 `PermissionGate` 内加 `enabled` 标志——gate 本身是通用组件，不应内嵌 agent 配置概念。

### D2：调用侧（normalizer / agent_app）负责读配置并传参

`normalizer.route()` 和 `agent_app.py` 的 `/chat` 路由已读取 `AgentFile`，在此读取
`permission_gate_enabled` 和超时值，构造 gate 实例后传入 `loop.run()`。loop 本身不读
`AgentFile`，保持无副作用。

### D3：`_default_gate` 保留用于无 agent 上下文的路径

`server.py` 的平台 `/chat` 路由和 `/approvals` 端点继续使用 `_default_gate`（无 agent 文件）。
agent_app.py 的 `/approvals` 端点改用同一 per-call gate（通过 `_default_gate` 仍可 resolve，
因为 `approval_id` 是全局唯一的 UUID）。

## Risks / Trade-offs

- **[Risk] per-call gate 实例导致 resolve 失败**：`request_approval` 和 `resolve` 须在同一
  gate 实例上调用。`_default_gate` 是全局的，per-call gate 不是。
  → **缓解**：`_plan_tool_slots` 向 `_default_gate` 发 approval 请求仍走全局单例（用于 resolve
  路径）；per-call gate 只用于 timeout 配置，resolve 仍委托 `_default_gate`。
  实际实现：把 `medium_timeout` / `high_timeout` 传给 `_default_gate.request_approval()`
  的调用，而非创建新实例——通过在调用处 override timeout 参数实现（见下方 D4）。

### D4（修订 D1）：timeout 通过参数传入 `request_approval` 而非新建 gate 实例

`PermissionGate.request_approval()` 新增可选 `medium_timeout` / `high_timeout` 参数，覆盖实例
默认值。这样 resolve 仍走 `_default_gate`，无实例分裂问题。

## Migration Plan

- 无数据迁移；字段新增且默认值 `true` 保持现有行为不变
- 现有不带 `permission_gate_enabled` 的 `agent.yaml` 继续以原行为运行

## Open Questions

无。
