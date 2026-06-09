# action-gate Specification

## Purpose
TBD - created by archiving change action-gate. Update Purpose after archive.
## Requirements
### Requirement: 风险等级映射到处置 mode

Action Gate SHALL 把工具的风险等级映射为四种处置 mode 之一：DIRECT（直接执行）、SANDBOX（容器内隔离执行）、APPROVAL（人工审批门）、REJECT（拒绝执行）。none/low 风险 SHALL 映射 DIRECT；medium/high 风险的 mode SHALL 可经配置（默认 APPROVAL）。

#### Scenario: 低风险直跑
- **WHEN** 工具风险为 none 或 low
- **THEN** mode 为 DIRECT，不经审批直接进入执行批

#### Scenario: medium/high 默认走审批
- **WHEN** 工具风险为 medium 或 high 且未改配置
- **THEN** mode 为 APPROVAL，经人工审批门

### Requirement: CRITICAL 硬编码拒绝且不可绕过

CRITICAL 风险的工具 SHALL 无条件映射 REJECT；该映射 MUST NOT 被任何配置覆盖，MUST NOT 被 pre_tool_use hook 的 ask 升降级改变，也 MUST NOT 被 LLM 提供的参数绕过。被拒的工具调用 SHALL 产生拒绝占位结果且不实际派发执行。

#### Scenario: critical 工具被拒
- **WHEN** 工具风险为 critical（无论 medium_mode/high_mode 如何配置、无论 hook 是否 ask）
- **THEN** mode 为 REJECT，工具不执行，返回明确的拒绝说明

### Requirement: 证明不了安全时 fail-closed 升级

当无法确定安全处置时，Action Gate SHALL 向更严格的 mode 升级而非放行：未识别的风险字符串 SHALL 映射 APPROVAL；解析为 SANDBOX 但工具并非 sandbox-backed（无法保证容器隔离）SHALL 升级为 APPROVAL。

#### Scenario: 未知风险升级审批
- **WHEN** 工具风险是未识别的字符串
- **THEN** mode 为 APPROVAL，而非 DIRECT

#### Scenario: 非沙箱工具的 sandbox 配置被升级
- **WHEN** medium_mode 配为 sandbox，但该工具不是 sandbox-backed
- **THEN** mode 升级为 APPROVAL（无法保证隔离）

### Requirement: 风险定级只来自服务端注册表（反逃逸）

工具的风险等级 SHALL 仅由服务端工具注册表（按工具名）决定，MUST NOT 从 LLM 提供的 tool_args 推断或被其覆盖。

#### Scenario: 参数无法降级 critical
- **WHEN** LLM 在 tool_args 中放入 `risk`/`risk_level` 等字段试图降低一个 critical 工具的等级
- **THEN** 定级仍来自注册表，工具仍被 REJECT

### Requirement: 联系不到审批人时拒绝

当一次调用路由到 APPROVAL 但无法联系到任何审批人时，Action Gate SHALL 拒绝该调用（default-closed），而非放行或无限等待。

#### Scenario: 无人可审即拒绝
- **WHEN** 工具需审批但 reply_func 联系不到任何审批人
- **THEN** 该调用被拒绝，工具不执行

