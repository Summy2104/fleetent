## Why

agent 危险操作目前只有「medium/high → 审批门」一条路由（`runtime/loop.py` `_plan_run_slots`），缺两件事：① **没有不可逾越的拒绝档**——再危险的操作（删库、改权限、外发大量数据等 CRITICAL 级）也只是走审批，人一旦点批就放行，没有「结构上禁止」的兜底；② **风险→处置方式硬编码**（`risk in ("medium","high")`），无法按部署策略把「已被 sandbox 结构性隔离的 medium 操作」降为无审批直跑（审批最小化），也无法表达「sandbox / 审批 / 拒绝」这几种不同处置。

本 change 把这条隐式分支抽成显式的 **Action Gate**：四级风险（LOW/MEDIUM/HIGH/CRITICAL）→ 四种处置 mode（direct/sandbox/approval/reject）的可配置路由，**CRITICAL 硬编码 reject 不可被配置或 LLM 绕过**，并对「证明不了安全」的情况一律 fail-closed 升级。

## What Changes

- **新增 `governance/action_gate.py`**：`ActionMode` 枚举（DIRECT/SANDBOX/APPROVAL/REJECT）+ 纯函数 `resolve_action_mode(risk, *, medium_mode, high_mode, sandbox_capable, force_ask)`：
  - **CRITICAL → REJECT，硬编码**：无视任何配置，永不放行。
  - none/low → DIRECT；medium → `medium_mode`；high → `high_mode`。
  - **fail-closed**：未知 risk 字符串 → APPROVAL（证明不了安全就升级）；mode 解析为 SANDBOX 但工具非 sandbox-backed → 升级为 APPROVAL（无法保证容器隔离就要人审）。
  - pre_tool_use hook 的 `ask` → APPROVAL（CRITICAL 仍 reject，ask 不能降级 critical）。
- **`runtime/loop.py` `_plan_run_slots` 用 Action Gate 替换硬编码分支**：REJECT → placeholder 拒绝（`counts_failure=False`，不触发审批）；APPROVAL → 复用既有 `request_approval`；DIRECT/SANDBOX → 进入执行批（sandbox-backed 工具本身在容器内自隔离，gate 不重复包一层）。
- **配置（agent.yaml → GovernanceConfig）**：新增 `action_gate_medium_mode`（默认 `approval`）、`action_gate_high_mode`（默认 `approval`）。**默认映射与既有 approval-routing 契约完全一致**（medium/high→approval），只是现在可配置成 `sandbox`/`direct`（如把已沙箱化的 medium 操作降为 sandbox 无审批，落地「审批最小化」）。
- **反逃逸**：risk 等级只从 registry（`get_risk_level`，服务端、按工具固定）取，**绝不从 LLM 提供的 tool_args 推断**——LLM 无法通过构造参数把 critical 工具降级。
- **no_reply → reject**：复用 permission_gate 既有 default-closed 行为（联系不到审批人即拒绝），本 change 加回归测试锁定该语义为 Action Gate 的「联系不到人 = 拒绝」契约。

> **对既有 approval-routing 的影响**：默认行为零变化（medium/high 仍走审批、low/none 仍直跑）。唯一新增的运行时行为是 **CRITICAL 工具被无条件拒绝**——当前代码库尚无 critical 级工具注册，故对现有工具零影响；它是为后续把真正危险操作标 critical 提供结构性兜底。`sandbox`/`direct` 作为 medium/high 的可选 mode 由部署显式开启。

## Capabilities

### New Capabilities
- `action-gate`: 风险→处置的显式门控契约——四级风险映射到 direct/sandbox/approval/reject 四种 mode；CRITICAL 硬拒不可配置/不可绕过；未知风险与无法保证 sandbox 隔离时 fail-closed 升级；risk 仅来自服务端 registry（反 LLM 参数降级）；medium/high 的 mode 可经 agent.yaml 配置，默认保持既有审批路由。

### Modified Capabilities
<!-- 无：permission-gate 的审批契约被复用、不改；本 change 在其上叠加风险→mode 的前置路由。 -->

## Impact

- **代码**：新增 `governance/action_gate.py`；`runtime/loop.py`（`_plan_run_slots` 路由分支）；`runtime/snapshot.py`（GovernanceConfig 两个字段）；`agent_config.py`（AgentFile 两个字段 + 校验）。
- **约束**：纯 agent 运行时（governance/ + runtime/），不依赖 platform；不改 permission_gate 契约、不改 run_stream（streaming-approval-gating 为独立未合并 change，本 change 不碰）。
- **测试**：unit（resolve_action_mode 全档/critical 硬拒/fail-closed 升级/未知风险/sandbox 能力缺失升级/force_ask；loop 集成：critical→拒绝、medium/high→审批不变、配置 sandbox→无审批直跑；反逃逸：args 不能降级；no_reply→reject 回归）。
- **依赖**：基于已合并入 main 的 approval-routing（permission_gate + approval_store）。
