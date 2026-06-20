## Why

审批门统一化(R1 agent-owned-approval)后,`reflection_gate.resolve_review_channel`(及其返回类型 `ReviewRoute`)成了死代码:生产侧零调用、硬编码 `return "im"`,只剩自身定义 + 4 个测试引用。真实的审批渠道路由由 `agent_config.resolve_approvers` + `permission_gate._notify_approvers`(统一外呼)承担,与 `self-evolution-split` spec「审批渠道按 proposal 类型路由」一致。本 change 清掉这撮残留,让 `reflection_gate` 只保留"统一 router 背后按 subject_type 分派的 handler"职责。

## What Changes

- 删除 `reflection_gate.resolve_review_channel` 函数与 `ReviewRoute = Literal["im"]` 类型别名。
- 删除 `tests/unit/test_reflection_gate.py` 中 4 个 `test_resolve_review_channel_*` 测试。

**不动**(已核实为 live):`_shared_memory_reviewer` / `set_shared_memory_reviewer` / `_default_shared_memory_reviewer`(行 ~496 决定 apply actor)、`_load_proposal_type`(live resolve 共用)、统一审批三侧(approval_requests / approval_router / resolve_approvers 通知)。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `self-evolution-split`:MODIFY「审批渠道按 proposal 类型路由」——明确审批渠道仅经 `resolve_approvers` 解析、不得另设独立 review-channel helper(固化清理后状态,防死 helper 重生)。行为不变。

## Impact

**owning package**:`src/fleetent/governance/reflection_gate.py`(删 1 函数 + 1 类型别名);`tests/unit/test_reflection_gate.py`(删 4 测试)

**public API surface**:无(`resolve_review_channel` 未导出、生产零调用)

**owned tables**:无　**config namespace**:无　**migration**:无

**cross-module dependencies**:无变化;`reflection_gate` 仍是 `approval_router` 分派 memory/skill 的 handler

**行为影响**:零——被删函数无任何生产调用方,审批渠道路由实际由 `resolve_approvers` 承担(不变)
