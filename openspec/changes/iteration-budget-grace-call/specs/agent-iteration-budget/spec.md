## ADDED Requirements

### Requirement: 三维迭代预算

主循环 SHALL 在三个维度上度量并约束单次任务的预算：执行步数、token 用量、美元成本。当任一维度达到其配置上限时，预算判定 MUST 认定预算耗尽。每个维度的上限 MUST 可通过参数注入或配置覆盖默认值，且 MUST 支持「该维度无上限」。

#### Scenario: 步数维度达上限触发预算耗尽
- **WHEN** 任务执行步数达到配置的步数上限
- **THEN** 预算判定认定预算耗尽，并可报出触发维度为步数

#### Scenario: token 维度达上限触发预算耗尽
- **WHEN** 累计 token 用量达到配置的 token 上限
- **THEN** 预算判定认定预算耗尽，触发维度为 token

#### Scenario: 成本维度达上限触发预算耗尽
- **WHEN** 累计美元成本达到配置的成本上限
- **THEN** 预算判定认定预算耗尽，触发维度为美元成本

#### Scenario: 无上限维度不触发
- **WHEN** 某维度配置为无上限
- **THEN** 该维度的累计用量无论多大都不触发预算耗尽

### Requirement: 预算判定注册进终止框架

预算判定 SHALL 实现为一个独立的终止 checker 并注册到 `TerminationController`，复用预留的 `budget_exceeded` 原因码。接入预算判定 MUST NOT 修改主循环已有的 `consecutive_failures` / `approval_rejected` 判定分支。

#### Scenario: 预算 checker 参与每轮评估
- **WHEN** 主循环构建终止控制器
- **THEN** 预算 checker 被注册并参与每轮终止评估

#### Scenario: 预算耗尽以 budget_exceeded 终止
- **WHEN** 预算判定在某轮认定预算耗尽
- **THEN** 主循环以 `budget_exceeded` 原因进入终止收尾

### Requirement: 系统内部操作豁免计入预算

只有为推进用户任务而发起的主循环 LLM 调用 SHALL 计入预算用量。上下文压缩等系统内部操作产生的 token 与成本 MUST NOT 计入任务预算。

#### Scenario: 主循环 LLM 调用计入预算
- **WHEN** 主循环为推进任务发起一次 LLM 调用
- **THEN** 该次调用的步数、token、成本计入预算用量

#### Scenario: 压缩调用不计入预算
- **WHEN** 上下文压缩触发其内部的摘要 LLM 调用
- **THEN** 该次内部调用的 token 与成本不计入任务预算用量

### Requirement: 预算耗尽时触发 Grace Call 生成进展总结

当预算判定认定预算耗尽时，主循环 MUST NOT 直接以空或半截结果收尾，而 SHALL 发起最后一次 LLM 调用（Grace Call），指示 AI 生成「当前进展与已得结论」的总结，并以该总结作为最终回复，随后以 `budget_exceeded` 原因终止。Grace Call MUST NOT 再请求工具调用。

#### Scenario: 预算耗尽生成总结而非硬切断
- **WHEN** 任务在某轮被判定预算耗尽
- **THEN** 主循环发起一次 Grace Call 生成进展总结，并以该总结作为最终回复返回给用户，而非返回空响应

#### Scenario: budget_exceeded 终止记录原因码与触发维度
- **WHEN** 任务因预算耗尽经 Grace Call 收尾终止
- **THEN** 该次运行的 trace 记录中包含 `budget_exceeded` 原因码及触发预算耗尽的维度

#### Scenario: 流式路径下 Grace Call 总结以流式增量送达
- **WHEN** `run_stream()` 在某轮检查点判定预算耗尽
- **THEN** 主循环发起一次流式 Grace Call，将进展总结以 `text_delta` 增量流给客户端，随后以 `done` 收尾并记录 `budget_exceeded`，不向客户端泄漏半截工具循环

#### Scenario: 流式 Grace Call 已流出部分增量后失败仍以 done 收尾
- **WHEN** `run_stream()` 的 Grace Call 已 yield 部分 `text_delta` 后中途失败
- **THEN** 主循环以已流出的部分内容收尾、`yield done` 并记录降级，不回滚已流出增量、不重试、不抛出未处理异常

### Requirement: Grace Call 使用按固定比例预留的独立 token 预算

Grace Call SHALL 使用从主任务 token 预算按固定比例预留的独立 token 上限：`grace_max_tokens = max(round(max_tokens × ratio), floor)`。预留比例（默认 0.05）与保底 token 下限（默认 512）MUST 可通过配置覆盖。

#### Scenario: 预留比例计算 Grace Call 上限
- **WHEN** 主任务 token 上限与预留比例确定
- **THEN** Grace Call 的 token 上限为「主上限 × 比例」与保底下限二者中的较大值

#### Scenario: 小预算下取保底下限
- **WHEN** 主任务 token 上限很小，使「上限 × 比例」低于保底下限
- **THEN** Grace Call 的 token 上限取保底下限，保证能生成有效总结

#### Scenario: 预留比例与下限可配置
- **WHEN** 通过配置覆盖预留比例或保底下限
- **THEN** Grace Call 的 token 上限按覆盖后的值计算

### Requirement: Grace Call 自身失败降级为部分结果

当 Grace Call 自身失败（报错、超时或返回空）时，主循环 MUST 返回任务终止前已累积的部分结果，记录降级，且 MUST NOT 重试 Grace Call、MUST NOT 因此崩溃。

#### Scenario: Grace Call 失败返回已有部分结果
- **WHEN** Grace Call 的 LLM 调用失败或返回空
- **THEN** 主循环返回终止前已累积的最后一段内容作为回复，记录该次降级，不重试、不抛出未处理异常

### Requirement: 预算计量维度接口对外契约

预算计量维度（步数 / token / 美元成本）与用量累计口径 SHALL 作为对外契约供后续多层级预算与成本感知路由复用。后续需求 MUST 能在不改变本计量维度集合与累计口径（含豁免语义）的前提下，叠加预算层级或读取用量做路由决策。

#### Scenario: 多层级预算复用计量口径
- **WHEN** 后续需求在单次任务预算之上叠加更多预算层级
- **THEN** 它复用同一组计量维度与用量累计口径，无需引入并行的另一套计量机制

#### Scenario: 路由决策读取同一用量
- **WHEN** 后续成本感知路由需要据用量做决策
- **THEN** 它读取本契约定义的用量累计结果，计量口径与预算判定一致

### Requirement: budget_exceeded 终止已接入主循环

预算 checker SHALL 注册进终止框架并使 `budget_exceeded` 成为可触发的终止原因（此前为框架中已定义但无 checker、永不触发的预留原因码）。当任一预算维度（步数 / token / 美元成本）达到上限时，已注册的预算 checker MUST 以 `budget_exceeded` 原因触发 Grace Call 收尾与终止，并复用既有 `stop_reason` 出口写入 trace。接入预算 checker MUST NOT 修改主循环已有的 `consecutive_failures` / `approval_rejected` 判定分支与优先级。

#### Scenario: budget_exceeded 已接入并可触发
- **WHEN** 任一预算维度（步数 / token / 美元成本）达到上限
- **THEN** 已注册的预算 checker 以 `budget_exceeded` 原因触发 Grace Call 收尾与终止

#### Scenario: 接入不改动 consecutive_failures / approval_rejected 判定
- **WHEN** 注册预算 checker 后主循环进入每轮终止评估
- **THEN** `consecutive_failures` / `approval_rejected` 的判定与优先级不变

## MODIFIED Requirements

### Requirement: max_turns 终止

主循环 SHALL 跟踪迭代轮数，并将其作为三维预算的「步数」维度纳入预算判定；当轮数达到配置的步数上限时，预算判定 MUST 认定预算耗尽，并经 Grace Call 收尾后以 `budget_exceeded` 原因终止当次任务（而非旧的硬切断 `max_turns` 收尾）。`StopReason.max_turns` 枚举成员 MUST 保留以兼容既有引用与历史 trace，但主循环 MUST NOT 再以 `max_turns` 作为步数维度命中时的终止原因码——步数维度命中由预算判定统一产出 `budget_exceeded`（触发维度记为步数）。该上限 MUST 可通过参数注入或配置覆盖默认值。

#### Scenario: 达到步数上限经 Grace Call 终止并产出 budget_exceeded
- **WHEN** 主循环迭代轮数达到步数上限且 LLM 仍在请求工具
- **THEN** 预算判定认定预算耗尽，主循环发起 Grace Call 生成进展总结后以 `budget_exceeded` 原因（触发维度为步数）终止，不再发起新的工具循环，且不以 `max_turns` 作为该次终止的原因码

#### Scenario: 未达上限时不受影响
- **WHEN** 迭代轮数未达步数上限且其它预算维度未耗尽
- **THEN** 预算判定不触发终止
