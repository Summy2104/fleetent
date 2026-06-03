## MODIFIED Requirements

### Requirement: max_turns 终止

主循环 SHALL 跟踪迭代轮数，并将其作为两维预算的「步数」维度纳入预算判定；当轮数达到配置的步数上限时，预算判定 MUST 认定预算耗尽，并经 Grace Call 收尾后以 `budget_exceeded` 原因终止当次任务（而非旧的硬切断 `max_turns` 收尾）。`StopReason.max_turns` 枚举成员 MUST 保留以兼容既有引用与历史 trace，但主循环 MUST NOT 再以 `max_turns` 作为步数维度命中时的终止原因码——步数维度命中由预算判定统一产出 `budget_exceeded`（触发维度记为步数）。该上限 MUST 可通过参数注入或配置覆盖默认值。

#### Scenario: 达到步数上限经 Grace Call 终止并产出 budget_exceeded
- **WHEN** 主循环迭代轮数达到步数上限且 LLM 仍在请求工具
- **THEN** 预算判定认定预算耗尽，主循环发起 Grace Call 生成进展总结后以 `budget_exceeded` 原因（触发维度为步数）终止，不再发起新的工具循环，且不以 `max_turns` 作为该次终止的原因码

#### Scenario: 未达上限时不受影响
- **WHEN** 迭代轮数未达步数上限且其它预算维度未耗尽
- **THEN** 预算判定不触发终止
