## Context

完整设计见 `docs/hooks-system-design-decisions.md`（架构 A、9 钩子点、4 批）。本 change 实现 P1：引擎 + `pre_tool_use`。工具准入现处于 `loop._plan_run_slots`（~675：`get_risk_level` → `_default_gate.request_approval`）与 `run_stream` 的内联 plan 循环；`allowed_tools` 白名单在 schema 级（`check_tool_access`）。

## Goals / Non-Goals

**Goals:** 引擎（契约+派发+隔离+超时+默认关闭+加载）+ pre_tool_use 接既有准入。

**Non-Goals:** P2–P4 的其它钩子点；shell hook（永久不做）；nested `hooks:` 配置（用扁平 governance 字段，与现有一致）。

## Decisions

### D1：引擎独立、纯机制（架构 A）
`runtime/hooks.py` 不 import loop/governance/tools。`dispatch(event, ctx, *, timeout, strict)` 用 `asyncio.wait_for` 包每个 hook（sync 经 `asyncio.to_thread` 或直接调，async 直接 await）；异常/超时 → warn + 跳过；决策点 `deny` 短路、`strict` 时失败=deny、`open` 时失败=放行+审计；变换点把 `modified_*` 链式回灌进 ctx。`has_hooks(event)` 让调用方零开销跳过。

### D2：配置扁平化（与既有 governance 一致）
`AgentFile` + `GovernanceConfig` 加 `hooks_enabled: bool=False` / `hooks_decision_failure: str="open"` / `hooks_timeout_seconds: float=5.0`；`_governance_from_file` 映射。（设计文档里的 nested `hooks:` 仅示意；落地用扁平字段，省映射代码、与 steering_* 等同模式。）

### D3：pre_tool_use 在既有准入点组合
`_plan_run_slots`：在 `get_risk_level`/`request_approval` 处，若 `governance.hooks_enabled and hooks.has_hooks("pre_tool_use")` → `dispatch`：`deny`→产出拒绝 placeholder（复用现有拒绝路径，`counts_failure=False`）；`modified_args`→替换该 tc 的 args；`ask`→把该工具视作需审批（即使 risk 低）走 `request_approval`；`proceed`→继续。run_stream 内联 plan 同样处理。不新建准入点。

### D4：加载零改 plugin_loader
`@hook` 注册是 import 副作用；plugin_loader 已 import 启用插件包 → hook 自动注册。确认 run/run_stream 路径已触发插件加载（CLI `run_sync` 已 `load_plugins`；server/IM 路径若未触发，补一次 best-effort 加载——作为本 change 的接线子项）。

## Risks / Trade-offs

- **[Risk] dispatch 在工具热路径**：`has_hooks` + `hooks_enabled` 双门确保未用时零开销；超时防挂起。
- **[Risk] ask 强制审批但 run_stream 不审批**：流式路径当前不走 permission_gate（设计如此）；流式上 `ask` 退化为 `deny`+提示（记录），避免静默放行。文档化。
- **[Trade-off] 扁平配置 vs nested**：扁平省代码、与现状一致；牺牲一点分组美观。
