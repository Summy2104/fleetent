# self-evolution-split Specification

## Purpose
固化 reflection 自进化能力的三刀切归属：自进化引擎为顶层 agent 元能力、变更审批门为 governance 异步泛化、管理 API 为 platform 薄壳（reflection_management），并以护栏破除 memory↔reflection 循环。
## Requirements
### Requirement: 自进化引擎作为顶层 agent 元能力

reflection 自进化引擎 SHALL 作为顶层 agent 元能力存在（`src/fleetent/reflection/`），纵向贯穿各能力域。它 SHALL 读 trace / `memory` / `knowledge_base.retrieval` 产出 finding 与改进 proposal，SHALL NOT 直接执行变更（变更经审批门）。引擎 MUST NOT import `knowledge_base.ingest`、MUST NOT import `fleetent.platform.*`。本阶段引擎内部不再细分（memory/KB/skill 反思暂留一块）。

#### Scenario: 引擎只读不直接写
- **WHEN** 自进化引擎运行
- **THEN** 它 SHALL 只读 trace/memory/KB.retrieval 并产出 proposal
- **AND** 变更落地 SHALL 经审批门，引擎本身 SHALL NOT 直接写真相源

#### Scenario: 引擎不依赖摄取与控制面
- **WHEN** 检查 `reflection` 引擎的 import
- **THEN** SHALL NOT 出现对 `knowledge_base.ingest` 或 `fleetent.platform.*` 的 import

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

### Requirement: 审批渠道按 proposal 类型路由

**agent 侧自进化提案**(agent 自有域:user memory / skill)的审批门 SHALL 按 proposal 类型解析**审批人**(由影响范围决定找谁):user memory → 该 memory 的 **owner**(该 user 本人,owner 同意对自己记忆的改动);skill → agent 归属 **team / tenant 负责人**(admin)。**触达渠道统一为 agent-owned 外呼**——经 `agent_config.resolve_approvers`(读 agent.yaml `ApprovalRouting`)解析审批人地址 + im_gateway **DM**(+ Slack 按钮 / 文本命令)触达,全在 agent 侧、**default-closed**(找不到审批人不自动 apply)。审批渠道 SHALL 仅由 `resolve_approvers` 解析,**不得**另设独立的 review-channel 路由 helper(统一前的 `resolve_review_channel` 已移除)。审批动作 MUST NOT 经 platform console;platform console SHALL 仅作**只读投影**(查看提案 / 审批历史),不是审批渠道。(本要求由 R1 `agent-owned-approval` / `approval-suspend-resume` 统一为 agent 侧外呼,取代原 skill/KB 经 platform console 审的旧路由。)**KB 不在此路由内**:KB 是 agent 只读的租户共享资源,不产 agent 侧提案;其 remediation(及对应审批)由 platform / 摄取面承担(读 agent 的 KB report 投影后处理),不经 agent 侧自进化审批门。

#### Scenario: 个人记忆找 owner、agent 侧外呼
- **WHEN** 门处理 user memory proposal
- **THEN** 它 SHALL 经 agent-owned 外呼 DM 推送给该 memory 的 owner(该 user 本人)
- **AND** 该路由 SHALL NOT 依赖 platform

#### Scenario: skill 找 team/tenant 负责人、经 DM 非 console
- **WHEN** 门处理 skill proposal
- **THEN** 它 SHALL 经 `resolve_approvers` 解析 agent 归属 team / tenant 负责人(admin)并经 im_gateway DM 触达
- **AND** 审批动作 SHALL NOT 经 platform console(console 仅供只读查看)

#### Scenario: 审批渠道无独立 review-channel helper
- **WHEN** 审批门为任一 proposal 类型解析触达渠道
- **THEN** 仅经 `resolve_approvers` 解析,代码中不存在独立的 `resolve_review_channel` / `ReviewRoute` 路由 helper

#### Scenario: KB 不走 agent 侧自进化审批门
- **WHEN** KB reflection 产生 finding
- **THEN** 不在 agent 侧创建 KB proposal、不经此审批门;KB remediation 由 platform / 摄取面处理

#### Scenario: 无审批人 default-closed
- **WHEN** agent 自有域 proposal 解析不到可达审批人
- **THEN** 提案保持 pending、不自动 apply,不回退到 platform console

### Requirement: 管理 API 作为 platform 薄壳（reflection_management）

reflection 的管理 API（list/get proposal、趋势查询、skill/KB console 评审暴露面）SHALL 位于 `platform/reflection_management/`，作为读 agent 侧 reflection 存储的薄壳。proposal/report SHALL 存为 **agent 数据**（自进化产物），管理 API SHALL 只读它、不持有能力本体。skill proposal 的评审暴露面 SHALL 由 reflection_management 提供，`skill_management` 评审 inbox 改为消费它。

#### Scenario: 管理 API 只读 agent 存储
- **WHEN** platform/reflection_management 列出或查询 proposal/趋势
- **THEN** 它 SHALL 读 agent 侧 reflection 存储
- **AND** 能力本体（引擎/门）SHALL NOT 因管理 API 移到 platform

### Requirement: 破 memory↔reflection 循环

memory SHALL NOT import reflection。reflection 引擎对 memory 的依赖 SHALL 只是**读**方向（reflection → memory）。**agent memory proposal** 的落地 SHALL 由审批门回调 **agent memory 写接口**完成（governance → memory 的 agent memory 写接口，方向正确），而非 memory 反向 import reflection。系统 SHALL 以 CI 护栏断言 `memory` MUST NOT import `reflection`。

#### Scenario: memory 不反依赖 reflection
- **WHEN** 护栏测试检查 `memory` 的 import
- **THEN** 若其中出现对 `reflection` 的 import，测试 SHALL 失败

#### Scenario: 提案落地经门居中
- **WHEN** agent memory proposal 被审批通过
- **THEN** 审批门 SHALL 回调 agent memory 写接口落地
- **AND** memory 侧 SHALL NOT 为此 import reflection

### Requirement: 公共 API 行为稳定

三刀切 SHALL NOT 改变 reflection 自进化/审批/管理的公共 API 行为与语义。调用方经新路径使用 reflection 引擎/门/管理 API 的行为 SHALL 与迁移前完全一致。

#### Scenario: 行为不变
- **WHEN** 调用方经新路径使用 reflection 引擎/门/管理 API
- **THEN** 其行为 SHALL 与迁移前完全一致
