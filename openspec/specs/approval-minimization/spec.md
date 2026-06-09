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

