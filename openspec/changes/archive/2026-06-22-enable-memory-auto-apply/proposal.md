## Why

reflection 的 auto-apply 机制端到端 plumbing 都在，却**从未被启用、也不安全**：

1. **永不触发**：`AutoMaintenancePolicy(allow_low_risk=False)` dataclass 存在，但全代码**零实例化**。
   `apply_memory_maintenance_proposal(..., auto_policy=None)` 的 `auto_policy` 参数一路传到底却始终是 None
   → `_auto_apply_allowed` 恒 False → 低风险 user-memory 维护**永远要人批**。`run_reflection` 也只生成+持久化、不 apply。
   结果：哪怕"标记本人某条记忆过期"这种零风险小事，也得人工点一次审批。

2. **现有判定不安全（正向白名单缺失）**：`_auto_apply_allowed` 用黑名单
   `action not in {delete, merge, rewrite, compact}`。但 `suggest_shared_memory_or_kb` 生成时
   `risk="low"` 且**不在黑名单** → 一旦 auto-apply 被启用，它会被自动应用，而该 action routes 到
   `shared_memory.apply_shared_memory_proposal`（写**共享记忆**）。共享记忆按治理应由 **team 审批人**批准
   （见车道 A 的 A4 决策），auto-apply 它等于**绕过 team 审批**。黑名单遗漏 = 安全洞。

现在做：把 auto-apply 真正接起来，并**默认 OFF + 仅 opt-in 启用**，同时把判定改成**正向白名单**堵住上述洞。
属车道 A 切片 A2，决策（默认 OFF、仅低风险非破坏 user-memory）已拍定。

## What Changes

- **配置开关（默认 OFF）**：`ReflectionSettings`（agent.yaml `reflection:` 命名空间）新增嵌套
  `auto_apply.allow_low_risk: bool = False`。只有显式置 true 才开。
- **接通触发**：scheduler 是自动化 owner。`agent_app` 读 `reflection.auto_apply.allow_low_risk` 构造
  `AutoMaintenancePolicy`，经 `start_reflection_scheduler(..., auto_policy=...)` →
  `_reflection_loop(..., auto_policy)` → `run_reflection(scope, *, auto_policy=None)` 线程传入。
  `run_reflection` 在 persist 各 memory 提案后，对**符合白名单**的执行 `apply_memory_maintenance_proposal(auto_policy=...)`。
  **不传 policy（手动 run_reflection / 测试）= 现状完全不变**。
- **判定改正向白名单（安全修复）**：`_auto_apply_allowed` 从黑名单改为
  `action in {"mark_stale"}`（owner 自己的 user-memory、非破坏的唯一低风险动作）+ `risk == "low"` + `policy.allow_low_risk`。
  显式排除 `suggest_shared_memory_or_kb`（写共享记忆、需 team 审批）和所有破坏性动作（delete/merge/rewrite/compact）。
  两处副本（`reflection.py` 与 `governance/reflection_gate.py`）一致更新。
- **舱壁化**：auto-apply 逐条独立 best-effort，单条失败只记日志、不影响其它提案、**绝不让 reflection loop 崩**。

**明确不做（属相邻切片）**：
- 不改 approver 找对人规则（A4）；shared/skill 提案的审批指派属 A4，本切片只确保它们**不被 auto-apply**。
- 不动平台 resolve 路径（A3）。
- 不接 skill 提案的 auto-apply（skill 永远要人批，spec 已有 "No automatic application" 对 skill 文件的约束保留）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `reflection`: "No automatic application" 需求加 opt-in 例外（默认仍不自动应用）；新增"opt-in 低风险 user-memory
  auto-apply"需求（默认 OFF、仅 mark_stale、排除 shared/破坏性、失败 best-effort）。

## Impact

- **owning package**：`reflection/`（run_reflection / scheduler / _auto_apply_allowed）、`governance/`（gate 的
  _auto_apply_allowed 副本）、`agent_config`（ReflectionSettings）、`runtime/agent_app`（构造并下传 policy）
- **public API surface**：`AutoMaintenancePolicy`（既有）；`run_reflection` 增 `auto_policy` kwarg；
  `start_reflection_scheduler` 增 `auto_policy` kwarg；`ReflectionSettings.auto_apply`
- **owned tables**：`reflection_proposals`（仅状态流转 pending→applied，无 schema 改动）
- **config namespace**：`reflection.auto_apply`（agent.yaml）——新增
- **cross-module dependencies**：`agent_app` 读 agent config 并构造 policy（既有 config 读取模式）；
  scheduler 与 run_reflection 同在 `reflection/`；无 agent→platform 反向依赖
- **migration / shim**：无迁移、无 schema 变动
- **受影响代码**：`src/fleetent/agent_config.py`、`src/fleetent/reflection/reflection.py`、
  `src/fleetent/reflection/scheduler.py`、`src/fleetent/runtime/agent_app.py`、
  `src/fleetent/governance/reflection_gate.py` + 相关单测
