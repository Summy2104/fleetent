## ADDED Requirements

### Requirement: 部署 mode 推荐选型指引

部署文档 SHALL 为全局沙箱三态 `mode`(`off` / `selective` / `all`)提供按部署形态的推荐选型指引,使部署者能依据信任边界与免审批意图选定 mode,并与"封闭即免审批"配套。该指引为**文档 / 指引性质**,MUST NOT 改变三态 `mode` 的语义、默认值,亦 MUST NOT 改变后端不可用时降级为 `off` 的行为。指引 SHALL 至少覆盖:封闭可信内网且希望兑现 medium 免审批的部署推荐 `all` 并将 `action_gate_medium_mode` 配为 `sandbox`;希望最小暴露代码执行面、仅授权 agent 可用的部署推荐 `selective`;需完全禁用代码执行的部署推荐 `off`。指引 MUST 明确:免审批仅在运行时封闭成立时生效(无 docker / 降级 `off` 时由 fail-closed 升审批),选 `off` 即不存在容器封闭、相应 medium 操作不会因 `sandbox` 配置免审批而是仍走审批。

#### Scenario: 封闭可信部署的推荐
- **WHEN** 部署形态为封闭可信内网、希望容器内 medium 操作免审批自动化
- **THEN** 指引推荐 `mode=all` 配合 `action_gate_medium_mode: sandbox`,且说明免审批仅在 `sandbox_capable` 为真时生效

#### Scenario: 最小暴露部署的推荐
- **WHEN** 部署形态希望最小暴露代码执行面、仅特定授权 agent 可用 `run_code`
- **THEN** 指引推荐 `mode=selective`,并说明仅 `code_execution=true` 的 agent 暴露 `run_code`

#### Scenario: 禁用代码执行部署的推荐
- **WHEN** 部署形态需完全禁用代码执行
- **THEN** 指引推荐 `mode=off`,并说明此形态下不存在容器封闭、medium 操作不会因 `sandbox` 配置免审批而仍走审批

#### Scenario: 指引不改变 mode 语义与降级行为
- **WHEN** 部署依指引选定某 mode
- **THEN** 三态 `mode` 的语义、默认值与后端不可用时降级为 `off` 的行为保持不变,指引仅提供选型建议
