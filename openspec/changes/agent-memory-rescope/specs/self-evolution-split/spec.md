## MODIFIED Requirements

### Requirement: 变更审批门作为 governance 异步泛化

reflection proposal 的变更审批门 SHALL 位于 `governance/`，作为 `permission_gate` 的**异步非阻塞泛化**（proposal 持久化、延后 resolve、不阻塞自进化），与 `permission_gate` 并列。门 `resolve()` 后 SHALL 回调对应真相源写接口落地：user memory → user memory 写接口；**agent memory → agent memory 写接口（`memory` 的 agent memory 写接口）**；skill → skill 库；KB → agent-curated 沉淀源（**不直接写 KB**，派生视图）。`governance` MUST NOT import `fleetent.platform.*`。

#### Scenario: 审批通过落地到真相源
- **WHEN** 审批门收到对某 proposal 的 approve 并 resolve
- **THEN** 门 SHALL 回调该 proposal 类型对应的真相源写接口
- **AND** KB 类型 SHALL 写 agent-curated 沉淀源，SHALL NOT 直接写 KB

#### Scenario: 异步不阻塞引擎
- **WHEN** 引擎产出 proposal
- **THEN** proposal SHALL 被持久化、自进化 SHALL NOT 阻塞等待审批
- **AND** 审批 SHALL 可在之后经渠道 resolve

### Requirement: 破 memory↔reflection 循环

memory SHALL NOT import reflection。reflection 引擎对 memory 的依赖 SHALL 只是**读**方向（reflection → memory）。**agent memory proposal** 的落地 SHALL 由审批门回调 **agent memory 写接口**完成（governance → memory 的 agent memory 写接口，方向正确），而非 memory 反向 import reflection。系统 SHALL 以 CI 护栏断言 `memory` MUST NOT import `reflection`。

#### Scenario: memory 不反依赖 reflection
- **WHEN** 护栏测试检查 `memory` 的 import
- **THEN** 若其中出现对 `reflection` 的 import，测试 SHALL 失败

#### Scenario: 提案落地经门居中
- **WHEN** agent memory proposal 被审批通过
- **THEN** 审批门 SHALL 回调 agent memory 写接口落地
- **AND** memory 侧 SHALL NOT 为此 import reflection
