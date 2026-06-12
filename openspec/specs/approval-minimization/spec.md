# approval-minimization Specification

## Purpose
TBD - created by archiving change approval-minimization. Update Purpose after archive.
## Requirements
### Requirement: 审批人可授予 allow-always 持久指纹

审批人 SHALL 能在批准一次工具调用时选择「永久允许」，对该调用的 (请求者, 工具, 参数) 指纹授予持久授权。授予 MUST 是审批人的显式动作（默认的批准只对本次生效，不授予持久允许），并持久化、可审计。

#### Scenario: approve always 授予持久允许
- **WHEN** 审批人通过 IM 回复 `approve always <approval_id>`
- **THEN** 该调用被批准，且其指纹被写入 allow-list 持久化

#### Scenario: 普通 approve 不授予
- **WHEN** 审批人回复 `approve <approval_id>`（不带 always）
- **THEN** 该调用被批准但不写入 allow-list，后续相同调用仍需审批

### Requirement: 命中 allow-list 的调用自动放行

当一次需审批的调用的指纹已在 allow-list 中时，审批门 SHALL 直接放行（返回已批准）且 MUST NOT 联系任何审批人；该自动放行 SHALL 留下可审计记录。

#### Scenario: 相同指纹自动放行
- **WHEN** 一个工具调用的 (请求者, 工具, 参数) 指纹已被授予 allow-always
- **THEN** 审批门直接返回 approved，不发审批通知，并记录一条自动放行审计

### Requirement: 指纹基于服务端规范化参数

指纹 SHALL 由服务端从 (请求者标识, 工具名, 规范化后的工具参数) 计算，对参数键序无关、对参数值敏感。不同请求者 / 不同工具 / 不同参数 SHALL 产生不同指纹，互不复用授权。

#### Scenario: 参数不同则不复用授权
- **WHEN** 某指纹已授予 allow-always，随后同工具但参数不同的调用到来
- **THEN** 其指纹不同，不命中 allow-list，仍按正常流程审批

#### Scenario: 参数键序不影响指纹
- **WHEN** 两次调用的参数对象键顺序不同但内容相同
- **THEN** 计算出的指纹相同

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

