## 1. Action Gate 纯函数 + mode 枚举

- [x] 1.1 Write failing unit tests `tests/unit/test_action_gate.py`：`resolve_action_mode` 全档——none/low→DIRECT、medium→medium_mode、high→high_mode；critical→REJECT（且配 medium_mode/high_mode 任意值、force_ask=True 均不改变 critical 的 REJECT）；未知 risk 字符串→APPROVAL（fail-closed）；mode 解析 SANDBOX 但 sandbox_capable=False→APPROVAL（fail-closed）；force_ask=True 把非 critical 升 APPROVAL；`is_sandbox_backed` 对 run_code/5 文件工具为 True、其他为 False（tests/unit）
- [x] 1.2 Implement `governance/action_gate.py`（`ActionMode` 枚举 + `resolve_action_mode` + `SANDBOX_BACKED_TOOLS`/`is_sandbox_backed`），pass unit tests

## 2. GovernanceConfig + AgentFile 配置字段

- [x] 2.1 Write failing unit tests：GovernanceConfig 默认 `action_gate_medium_mode=="approval"`/`action_gate_high_mode=="approval"`；AgentFile 接受 `direct|sandbox|approval`、拒绝非法值；`_governance_from_file` 透传两字段（tests/unit）
- [x] 2.2 Implement GovernanceConfig 两字段 + AgentFile 两字段（Literal 校验）+ `_governance_from_file` 透传，pass unit tests

## 3. loop 接入 Action Gate（替换硬编码风险分支）

- [x] 3.1 Write failing unit tests `tests/unit/test_loop_action_gate.py`（mock LLM + mock gate）：critical 工具→不调 gate、产 reject placeholder 且 `counts_failure=False`、置 `approval_rejected`；medium/high→仍调 `request_approval`（默认 approval 不变，回归）；配 medium_mode=sandbox 且工具 sandbox-backed→不调 gate、直接进执行批；配 medium_mode=sandbox 但工具非 sandbox-backed→仍调 gate（fail-closed）（tests/unit）
- [x] 3.2 Implement `_plan_run_slots` 用 `resolve_action_mode` 路由（REJECT/APPROVAL/DIRECT·SANDBOX 三分支），pass unit tests

## 4. 反逃逸 + no_reply→reject 契约

- [x] 4.1 Write failing unit tests：风险定级只来自 registry——tool_args 内塞 `risk`/`risk_level` 字段不改变 critical 工具被拒（反逃逸）；permission_gate 在 reply_func 联系不到审批人时返回非 approved → loop 拒绝执行（no_reply→reject 回归，permission_gate 用短超时）（tests/unit）
- [x] 4.2 Implement / 确认：定级路径不读 tool_args（如已满足则仅加 guard 测试）；no_reply→reject 复用 permission_gate default-closed，pass tests

## 5. 收尾验证

- [ ] 5.1 解耦验证：action_gate 零 platform import；模块依赖护栏测试通过；无 platform DB 环境下 gate 路由可用（critical→reject、low→direct 不依赖任何 DB）
- [ ] 5.2 全量收尾：`make test-pr` 全绿（含刚合并的 approval-routing 回归不破）＋ ruff format/check + mypy 改动文件 + integration 对照 main 基线无新增失败
