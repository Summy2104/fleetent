## ADDED Requirements

### Requirement: 封闭 medium 操作免审批兑现

部署 SHALL 能通过把 agent 的 `action_gate_medium_mode` 配置为 `sandbox`,使**运行时封闭**(`sandbox-containment-gating` 判定 `sandbox_capable` 为真,即容器在 namespace 内封闭执行)的 medium 风险操作经 action gate 解析为 `SANDBOX` 处置在容器内直跑、MUST NOT 逐次打扰审批人。该免审批 MUST 仅在封闭成立时生效;封闭不成立(无 docker / `effective_mode == OFF` / 非容器内执行)时 MUST 复用 action gate 既有 fail-closed 行为升级为 `APPROVAL`。该兑现 MUST 全部复用既有机制——`resolve_action_mode` 契约、`is_sandbox_backed` / `SANDBOX_BACKED_TOOLS` 集合、registry risk 常量 MUST NOT 因本能力被修改;免审批仅是部署侧对已封闭 medium 操作的配置选择,正当性绑定运行时封闭性而非工具的静态分类。高风险(high)操作 MUST NOT 随 medium 一同被此默认放松——`action_gate_high_mode` 的推荐默认保持 `approval`。

#### Scenario: 封闭时 sandbox 配置免审批直跑
- **WHEN** 部署把某 agent 的 `action_gate_medium_mode` 配为 `sandbox`,某 medium 操作运行时 `sandbox_capable` 为真(容器封闭执行)
- **THEN** 该操作经 action gate 解析为 `SANDBOX` 在容器内直跑,不发起审批、不打扰审批人

#### Scenario: 未封闭时仍 fail-closed 升审批
- **WHEN** 同样配 `action_gate_medium_mode: sandbox`,但运行时封闭不成立(无 docker 使 `effective_mode == OFF`,或操作非容器内执行使 `sandbox_capable` 为假)
- **THEN** 该 medium 操作经既有 fail-closed 升级为 `APPROVAL` 走审批,不以 sandbox 名义静默直跑

#### Scenario: 高风险不随 medium 放松
- **WHEN** 部署把 `action_gate_medium_mode` 配为 `sandbox` 兑现 medium 免审批,但未单独调 `action_gate_high_mode`
- **THEN** high 风险操作仍按 `action_gate_high_mode` 的默认 `approval` 走审批,免审批默认不波及高风险面
